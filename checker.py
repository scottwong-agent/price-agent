"""
checker.py — runs daily via GitHub Actions.
Reads the Tracking sheet, checks current prices via Duffel,
and sends an email alert if any price has changed.
"""

import os
import json
import smtplib
import requests
import gspread
import pandas as pd
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials

# ─── CONFIG FROM ENVIRONMENT VARIABLES ───────────────────────────────────────
# All secrets come from GitHub Actions secrets (set in repo Settings → Secrets)

DUFFEL_TOKEN   = os.environ["DUFFEL_TOKEN"]
NOTIFY_EMAIL   = os.environ["NOTIFY_EMAIL"]       # email to send alerts TO
GMAIL_USER     = os.environ["GMAIL_USER"]          # Gmail address to send FROM
GMAIL_PASSWORD = os.environ["GMAIL_PASSWORD"]      # Gmail App Password (not your login password)
SPREADSHEET_URL = os.environ["SPREADSHEET_URL"]

# Service account JSON stored as a single secret
GSHEETS_CREDS  = json.loads(os.environ["GSHEETS_CREDS_JSON"])

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
COLUMNS = ["DateStarted", "Category", "Item", "BasePrice", "Threshold", "Metadata", "Status"]

# ─── GOOGLE SHEETS ────────────────────────────────────────────────────────────

def get_worksheet():
    creds  = Credentials.from_service_account_info(GSHEETS_CREDS, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet  = client.open_by_url(SPREADSHEET_URL)
    return sheet.worksheet("Tracking")

def read_tracking():
    ws      = get_worksheet()
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=COLUMNS)
    return pd.DataFrame(records)

def update_base_price(ws, row_index, new_price):
    """Update the BasePrice cell for a given row (1-indexed, +1 for header)."""
    # Find the BasePrice column index
    header = ws.row_values(1)
    col    = header.index("BasePrice") + 1
    ws.update_cell(row_index + 2, col, new_price)  # +2: 1 for header, 1 for 0-index

# ─── DUFFEL FLIGHT SEARCH ─────────────────────────────────────────────────────

def search_flights(origin, dest, dep_date, cabin, return_date=None):
    """Search Duffel and return list of offers sorted by price."""
    headers = {
        "Authorization": f"Bearer {DUFFEL_TOKEN}",
        "Duffel-Version": "v2",
        "Content-Type": "application/json",
    }
    slices = [{"origin": origin, "destination": dest, "departure_date": dep_date}]
    if return_date:
        slices.append({"origin": dest, "destination": origin, "departure_date": return_date})

    payload = {
        "data": {
            "slices": slices,
            "passengers": [{"type": "adult"}],
            "cabin_class": cabin,
        }
    }
    try:
        res = requests.post(
            "https://api.duffel.com/air/offer_requests",
            json=payload,
            headers=headers,
            timeout=30,
        )
        if res.status_code in (200, 201):
            offers = res.json()["data"]["offers"]
            return sorted(offers, key=lambda x: float(x["total_amount"]))
        else:
            print(f"  Duffel error {res.status_code}: {res.text[:200]}")
            return []
    except Exception as e:
        print(f"  Request failed: {e}")
        return []

# ─── EMAIL ────────────────────────────────────────────────────────────────────

def send_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = NOTIFY_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
    print(f"  Email sent: {subject}")

def build_flight_row(offer):
    airline  = offer["slices"][0]["segments"][0]["operating_carrier"]["name"]
    dep_time = offer["slices"][0]["segments"][0]["departing_at"][:16].replace("T", " ")
    arr_time = offer["slices"][0]["segments"][-1]["arriving_at"][:16].replace("T", " ")
    stops    = len(offer["slices"][0]["segments"]) - 1
    price    = float(offer["total_amount"])
    return f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #eee">{airline}</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{dep_time}</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{arr_time}</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{"Nonstop" if stops==0 else f"{stops} stop"}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;font-weight:bold;color:#0066cc">${price:.2f}</td>
        </tr>"""

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"Price Check Run — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")

    df = read_tracking()
    active = df[df["Status"] == "Active"]

    if active.empty:
        print("No active items to check.")
        return

    ws         = get_worksheet()
    alerts     = []   # collect all alerts to send in one email

    for idx, row in active.iterrows():
        category  = row["Category"]
        item      = row["Item"]
        base_price = float(row["BasePrice"])
        threshold  = float(row["Threshold"])  # % drop to alert on
        metadata   = json.loads(row["Metadata"].replace("'", '"')) if isinstance(row["Metadata"], str) else {}

        print(f"\nChecking [{category}] {item}  (base: ${base_price:.2f}, alert if >{threshold}% drop)")

        if category == "Flight":
            origin   = metadata.get("origin", "")
            dest     = metadata.get("dest", "")
            date     = metadata.get("date", "")
            cabin    = metadata.get("cabin", "economy")

            if not all([origin, dest, date]):
                print("  Skipping — missing metadata")
                continue

            offers = search_flights(origin, dest, date, cabin)

            if not offers:
                print("  No offers returned")
                continue

            # ── 1. Cheapest available (any flight on route) ──────────────────
            cheapest_offer = offers[0]
            cheapest_price = float(cheapest_offer["total_amount"])
            cheapest_airline = cheapest_offer["slices"][0]["segments"][0]["operating_carrier"]["name"]

            # ── 2. Price change vs base ──────────────────────────────────────
            pct_change = ((cheapest_price - base_price) / base_price) * 100
            direction  = "dropped" if pct_change < 0 else "increased"
            print(f"  Current cheapest: ${cheapest_price:.2f} ({direction} {abs(pct_change):.1f}% vs base ${base_price:.2f})")

            # Build top 5 flights table for the email
            top_flights_rows = "".join(build_flight_row(o) for o in offers[:5])
            flights_table = f"""
                <table style="width:100%;border-collapse:collapse;font-size:14px">
                    <thead>
                        <tr style="background:#f5f5f5">
                            <th style="padding:8px;text-align:left">Airline</th>
                            <th style="padding:8px;text-align:left">Departs</th>
                            <th style="padding:8px;text-align:left">Arrives</th>
                            <th style="padding:8px;text-align:left">Stops</th>
                            <th style="padding:8px;text-align:left">Price</th>
                        </tr>
                    </thead>
                    <tbody>{top_flights_rows}</tbody>
                </table>"""

            # Always include a daily summary regardless of threshold
            change_color = "#cc0000" if pct_change > 0 else "#007700"
            change_text  = f"<span style='color:{change_color};font-weight:bold'>{direction} {abs(pct_change):.1f}%</span>"

            alert_html = f"""
                <div style="margin-bottom:30px;padding:20px;border:1px solid #ddd;border-radius:8px;font-family:sans-serif">
                    <h2 style="margin:0 0 4px">✈️ {origin} → {dest} | {cabin.title()}</h2>
                    <p style="color:#666;margin:0 0 16px">Date: {date}</p>
                    <p style="font-size:16px">
                        Cheapest today: <strong>${cheapest_price:.2f}</strong> on {cheapest_airline}
                        &nbsp;·&nbsp; {change_text} vs your base of ${base_price:.2f}
                    </p>
                    {"<p style='background:#fff3cd;padding:10px;border-radius:4px'>⚠️ <strong>ALERT:</strong> Price dropped past your " + str(int(threshold)) + "% threshold!</p>" if pct_change <= -threshold else ""}
                    <h3 style="margin:16px 0 8px">Top 5 Available Flights</h3>
                    {flights_table}
                </div>"""

            alerts.append(alert_html)

            # Update base price in sheet to today's cheapest so next run compares correctly
            update_base_price(ws, idx, cheapest_price)
            print(f"  Sheet updated: new base price = ${cheapest_price:.2f}")

    # ── Send one combined email with all alerts ──────────────────────────────
    if alerts:
        date_str = datetime.now().strftime("%b %d, %Y")
        body = f"""
            <html><body style="font-family:sans-serif;max-width:700px;margin:auto;padding:20px">
                <h1 style="border-bottom:2px solid #0066cc;padding-bottom:10px">
                    🕵️ Elite Price Report — {date_str}
                </h1>
                {"".join(alerts)}
                <p style="color:#999;font-size:12px;margin-top:30px">
                    Sent by your Elite Price Agent · Checks run daily at 8 AM UTC
                </p>
            </body></html>"""
        send_email(f"✈️ Daily Price Report — {date_str}", body)
    else:
        print("\nNo alerts to send.")

    print(f"\nDone — {len(active)} items checked.")

if __name__ == "__main__":
    main()
