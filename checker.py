"""
checker.py — runs daily via GitHub Actions.
Reads the Tracking sheet via CSV export, checks prices,
and sends an email summary with alerts if price changed.
"""

import os
import json
import smtplib
import requests
import gspread
import pandas as pd
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials

# ─── SECRETS FROM GITHUB ACTIONS ─────────────────────────────────────────────
DUFFEL_TOKEN       = os.environ["DUFFEL"]
SG_CLIENT_ID       = os.environ["SG"]
EMAIL_SENDER       = os.environ["SENDER"]
EMAIL_PASSWORD     = os.environ["EMAIL_PASSWORD"]
EMAIL_RECEIVER     = os.environ["RECIEVER"]
GSHEET_CSV_URL     = os.environ["GSHEET_CSV_URL"]
SPREADSHEET_URL    = os.environ["SPREADSHEET_URL"]
GSHEETS_CREDS_JSON = json.loads(os.environ["GSHEETS_CREDS_JSON"])

SCOPES  = ["https://www.googleapis.com/auth/spreadsheets"]
COLUMNS = ["DateStarted", "Category", "Item", "BasePrice", "Threshold", "Metadata", "Status"]

# ─── GOOGLE SHEETS ────────────────────────────────────────────────────────────

def get_worksheet():
    creds  = Credentials.from_service_account_info(GSHEETS_CREDS_JSON, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet  = client.open_by_url(SPREADSHEET_URL)
    return sheet.worksheet("Tracking")

def read_tracking():
    df = pd.read_csv(GSHEET_CSV_URL)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[COLUMNS].reset_index(drop=True)

def update_base_price(ws, row_index, new_price):
    header = ws.row_values(1)
    col    = header.index("BasePrice") + 1
    ws.update_cell(row_index + 2, col, new_price)

# ─── DUFFEL FLIGHT SEARCH ─────────────────────────────────────────────────────

def search_flights(origin, dest, dep_date, cabin, return_date=None):
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
            json=payload, headers=headers, timeout=30,
        )
        if res.status_code in (200, 201):
            return sorted(res.json()["data"]["offers"], key=lambda x: float(x["total_amount"]))
        print(f"  Duffel error {res.status_code}: {res.text[:200]}")
        return []
    except Exception as e:
        print(f"  Duffel request failed: {e}")
        return []

# ─── SEATGEEK TICKET SEARCH ───────────────────────────────────────────────────

def search_tickets(event_id):
    try:
        url = f"https://api.seatgeek.com/2/events/{event_id}?client_id={SG_CLIENT_ID}"
        r   = requests.get(url, timeout=15).json()
        return r.get("stats", {}).get("lowest_price")
    except Exception as e:
        print(f"  SeatGeek request failed: {e}")
        return None

# ─── EMAIL ────────────────────────────────────────────────────────────────────

def send_email(subject, html_body):
    msg            = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
    print(f"  Email sent: {subject}")

def flight_row_html(offer):
    airline = offer["slices"][0]["segments"][0]["operating_carrier"]["name"]
    dep     = offer["slices"][0]["segments"][0]["departing_at"][:16].replace("T", " ")
    arr     = offer["slices"][0]["segments"][-1]["arriving_at"][:16].replace("T", " ")
    stops   = len(offer["slices"][0]["segments"]) - 1
    price   = float(offer["total_amount"])
    return (
        "<tr>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'>{airline}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'>{dep}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'>{arr}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee'>{'Nonstop' if stops == 0 else str(stops) + ' stop'}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #eee;font-weight:bold;color:#0066cc'>${price:.2f}</td>"
        "</tr>"
    )

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"Price Check — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    df     = read_tracking()
    active = df[df["Status"] == "Active"]

    if active.empty:
        print("No active items to check.")
        return

    ws       = get_worksheet()
    sections = []

    for idx, row in active.iterrows():
        category   = row["Category"]
        item       = row["Item"]
        base_price = float(row["BasePrice"])
        threshold  = float(row["Threshold"])

        try:
            raw_meta = row["Metadata"]
            metadata = json.loads(raw_meta.replace("'", '"')) if isinstance(raw_meta, str) else {}
        except Exception:
            metadata = {}

        print(f"Checking [{category}] {item}  base=${base_price:.2f}  threshold={threshold}%")

        # ── FLIGHTS ──────────────────────────────────────────────────────────
        if category == "Flight":
            origin = metadata.get("origin", "")
            dest   = metadata.get("dest", "")
            date   = metadata.get("date", "")
            cabin  = metadata.get("cabin", "economy")

            if not all([origin, dest, date]):
                print("  Skipping — missing origin/dest/date in metadata")
                continue

            offers = search_flights(origin, dest, date, cabin)
            if not offers:
                print("  No offers returned from Duffel")
                continue

            current_price   = float(offers[0]["total_amount"])
            current_airline = offers[0]["slices"][0]["segments"][0]["operating_carrier"]["name"]
            pct_change      = ((current_price - base_price) / base_price) * 100
            dropped         = pct_change < 0
            alert_triggered = pct_change <= -threshold

            print(f"  Cheapest: ${current_price:.2f} on {current_airline}  ({pct_change:+.1f}%)")

            rows_html  = "".join(flight_row_html(o) for o in offers[:5])
            table_html = (
                "<table style='width:100%;border-collapse:collapse;font-size:14px'>"
                "<thead><tr style='background:#f5f5f5'>"
                "<th style='padding:8px;text-align:left'>Airline</th>"
                "<th style='padding:8px;text-align:left'>Departs</th>"
                "<th style='padding:8px;text-align:left'>Arrives</th>"
                "<th style='padding:8px;text-align:left'>Stops</th>"
                "<th style='padding:8px;text-align:left'>Price</th>"
                "</tr></thead><tbody>" + rows_html + "</tbody></table>"
            )

            change_color = "#cc0000" if not dropped else "#007700"
            change_arrow = "▲" if not dropped else "▼"
            alert_box = (
                "<p style='background:#fff3cd;padding:12px;border-radius:4px;margin:12px 0'>"
                f"⚠️ <strong>PRICE DROP ALERT</strong> — dropped past your {int(threshold)}% threshold!</p>"
                if alert_triggered else ""
            )

            section = (
                "<div style='margin-bottom:30px;padding:20px;border:1px solid #ddd;border-radius:8px'>"
                f"<h2 style='margin:0 0 4px'>✈️ {origin} → {dest} &nbsp;·&nbsp; {cabin.replace('_',' ').title()}</h2>"
                f"<p style='color:#666;margin:0 0 12px'>Departure: {date}</p>"
                f"<p style='font-size:16px'>Cheapest today: <strong>${current_price:.2f}</strong> on {current_airline} &nbsp;"
                f"<span style='color:{change_color}'>{change_arrow} {abs(pct_change):.1f}%</span>"
                f" vs your base of ${base_price:.2f}</p>"
                + alert_box
                + "<h3 style='margin:16px 0 8px'>Top 5 Available Flights</h3>"
                + table_html
                + "</div>"
            )
            sections.append(section)
            update_base_price(ws, idx, current_price)
            print(f"  Sheet updated — new base: ${current_price:.2f}")

        # ── SPORTS ───────────────────────────────────────────────────────────
        elif category == "Sports":
            event_id = metadata.get("event_id")
            if not event_id:
                print("  Skipping — no event_id in metadata")
                continue

            current_price = search_tickets(event_id)
            if current_price is None:
                print("  No price returned from SeatGeek")
                continue

            current_price   = float(current_price)
            pct_change      = ((current_price - base_price) / base_price) * 100
            dropped         = pct_change < 0
            alert_triggered = pct_change <= -threshold

            print(f"  Lowest ticket: ${current_price:.2f}  ({pct_change:+.1f}%)")

            change_color = "#cc0000" if not dropped else "#007700"
            change_arrow = "▲" if not dropped else "▼"
            alert_box = (
                "<p style='background:#fff3cd;padding:12px;border-radius:4px;margin:12px 0'>"
                f"⚠️ <strong>PRICE DROP ALERT</strong> — dropped past your {int(threshold)}% threshold!</p>"
                if alert_triggered else ""
            )

            section = (
                "<div style='margin-bottom:30px;padding:20px;border:1px solid #ddd;border-radius:8px'>"
                f"<h2 style='margin:0 0 4px'>🏀 {item}</h2>"
                f"<p style='font-size:16px'>Lowest ticket today: <strong>${current_price:.2f}</strong> &nbsp;"
                f"<span style='color:{change_color}'>{change_arrow} {abs(pct_change):.1f}%</span>"
                f" vs your base of ${base_price:.2f}</p>"
                + alert_box
                + "</div>"
            )
            sections.append(section)
            update_base_price(ws, idx, current_price)
            print(f"  Sheet updated — new base: ${current_price:.2f}")

    # ── Send email ────────────────────────────────────────────────────────────
    if sections:
        date_str = datetime.now().strftime("%b %d, %Y")
        body = (
            "<html><body style='font-family:sans-serif;max-width:700px;margin:auto;padding:20px'>"
            "<h1 style='border-bottom:2px solid #0066cc;padding-bottom:10px'>"
            f"🕵️ Daily Price Report — {date_str}</h1>"
            + "".join(sections)
            + "<p style='color:#aaa;font-size:12px;margin-top:30px'>"
            "Sent by Elite Price Agent · Runs daily at 8 AM UTC via GitHub Actions</p>"
            "</body></html>"
        )
        send_email(f"🕵️ Price Report — {date_str}", body)
    else:
        print("\nNo results to email.")

    print(f"\nDone — {len(active)} items checked.")

if __name__ == "__main__":
    main()
