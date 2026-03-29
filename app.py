import streamlit as st
import requests
import pandas as pd
import gspread
import traceback
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# ─── PAGE SETUP ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Elite Price Agent", layout="wide", page_icon="🕵️")

# ─── SESSION STATE INIT ───────────────────────────────────────────────────────
if "flight_offers" not in st.session_state:
    st.session_state.flight_offers = []
if "sport_events" not in st.session_state:
    st.session_state.sport_events = []

# ─── GSPREAD CONNECTION ───────────────────────────────────────────────────────
COLUMNS = ["DateStarted", "Category", "Item", "BasePrice", "Threshold", "Metadata", "Status"]
SCOPES  = ["https://www.googleapis.com/auth/spreadsheets"]

@st.cache_resource
def get_worksheet():
    s = st.secrets["connections"]["gsheets"]
    # Fix private key — Streamlit sometimes stores \n as literal backslash-n
    private_key = s["private_key"].replace("\\n", "\n")
    creds_dict = {
        "type":                        "service_account",
        "project_id":                  s["project_id"],
        "private_key_id":              s["private_key_id"],
        "private_key":                 private_key,
        "client_email":                s["client_email"],
        "client_id":                   s["client_id"],
        "auth_uri":                    "https://accounts.google.com/o/oauth2/auth",
        "token_uri":                   "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url":        "https://www.googleapis.com/robot/v1/metadata/x509/" + s["client_email"],
    }
    creds  = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet  = client.open_by_url(s["spreadsheet"])
    return sheet.worksheet("Tracking")

# ─── DEBUG PANEL (shows full error prominently) ───────────────────────────────
with st.expander("🔧 Connection Debug", expanded=True):
    try:
        ws = get_worksheet()
        st.success("✅ Google Sheets connected successfully!")
        st.caption(f"Worksheet: {ws.title} | Rows: {ws.row_count}")
    except Exception as e:
        st.error("❌ Connection failed — full error below:")
        st.text(traceback.format_exc())   # full traceback, always visible as plain text
        st.warning("Once fixed, remove or collapse this debug panel.")
        st.stop()  # Don't run the rest of the app if connection is broken

# ─── SHEET HELPERS ───────────────────────────────────────────────────────────

def read_sheet():
    try:
        ws      = get_worksheet()
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(records)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[COLUMNS].reset_index(drop=True)
    except Exception as e:
        st.error("❌ READ ERROR — full details:")
        st.text(traceback.format_exc())
        return None

def write_sheet(df):
    try:
        ws = get_worksheet()
        ws.clear()
        ws.append_row(COLUMNS)
        for _, row in df[COLUMNS].iterrows():
            ws.append_row([str(v) if v is not None else "" for v in row.tolist()])
        return True
    except Exception as e:
        st.error("❌ WRITE ERROR — full details:")
        st.text(traceback.format_exc())
        return False

def submit_track(category, item, current_price, threshold, metadata):
    with st.spinner("Saving to Google Sheets…"):
        existing = read_sheet()
        if existing is None:
            return
        new_row = pd.DataFrame([{
            "DateStarted": datetime.now().strftime("%Y-%m-%d"),
            "Category":    category,
            "Item":        str(item),
            "BasePrice":   float(current_price),
            "Threshold":   int(threshold),
            "Metadata":    str(metadata),
            "Status":      "Active",
        }])
        updated = pd.concat([existing, new_row], ignore_index=True)
        success = write_sheet(updated)
    if success:
        st.balloons()
        st.success(f"🎯 Now tracking: **{item}**")


# ─── UI ───────────────────────────────────────────────────────────────────────
st.title("🕵️ Elite Price Intelligence Agent")
st.caption("Live Price Tracking for Flight Routes & Sports Events")

tab1, tab2, tab3 = st.tabs(["✈️ Flights", "🏀 Sports", "📋 Watchlist"])

# ── TAB 1: FLIGHTS ────────────────────────────────────────────────────────────
with tab1:
    st.subheader("Track a Flight Route")
    c1, c2, c3 = st.columns(3)
    with c1:
        origin    = st.text_input("From (IATA)", "SFO").upper().strip()
        trip_type = st.selectbox("Trip Type", ["One-way", "Round-trip"])
    with c2:
        dest  = st.text_input("To (IATA)", "JFK").upper().strip()
        cabin = st.selectbox("Cabin Class", ["economy", "premium_economy", "business", "first"])
    with c3:
        dep_date = st.date_input("Departure Date", datetime.now() + timedelta(days=30))
        ret_date = None
        if trip_type == "Round-trip":
            ret_date = st.date_input("Return Date", datetime.now() + timedelta(days=37))

    f_threshold = st.slider("Alert me if price drops by %:", 5, 50, 10, key="flight_slider")

    if st.button("🔍 Find Cheapest Deals"):
        with st.spinner("Searching Duffel…"):
            try:
                headers = {
                    "Authorization": "Bearer " + st.secrets["DUFFEL_TOKEN"],
                    "Duffel-Version": "v2",
                    "Content-Type": "application/json",
                }
                slices = [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}]
                if trip_type == "Round-trip" and ret_date:
                    slices.append({"origin": dest, "destination": origin, "departure_date": str(ret_date)})
                payload = {"data": {"slices": slices, "passengers": [{"type": "adult"}], "cabin_class": cabin}}
                res = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers, timeout=30)

                if res.status_code in (200, 201):
                    offers = res.json()["data"]["offers"]
                    st.session_state.flight_offers = [
                        {
                            "price":     o["total_amount"],
                            "airline":   o["slices"][0]["segments"][0]["operating_carrier"]["name"],
                            "origin":    origin, "dest": dest,
                            "dep_date":  str(dep_date), "cabin": cabin,
                            "threshold": f_threshold,
                        }
                        for o in sorted(offers, key=lambda x: float(x["total_amount"]))[:3]
                    ]
                    if not st.session_state.flight_offers:
                        st.warning("No flights found for this route and date.")
                else:
                    st.error(f"Duffel API error {res.status_code}: {res.text[:300]}")
                    st.session_state.flight_offers = []
            except KeyError:
                st.error("⚠️ DUFFEL_TOKEN not found in Streamlit secrets.")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

    for i, offer in enumerate(st.session_state.flight_offers):
        with st.container(border=True):
            col_a, col_b = st.columns([3, 1])
            col_a.write(f"**{offer['airline']}** | {offer['origin']} ➔ {offer['dest']}")
            col_a.caption(f"Cabin: **{offer['cabin']}** | Date: {offer['dep_date']} | Price: **${offer['price']}**")
            if col_b.button(f"Track @ ${offer['price']}", key=f"f_btn_{i}"):
                submit_track("Flight", f"{offer['origin']}-{offer['dest']}", offer["price"], offer["threshold"],
                             {"origin": offer["origin"], "dest": offer["dest"], "date": offer["dep_date"], "cabin": offer["cabin"]})

# ── TAB 2: SPORTS ─────────────────────────────────────────────────────────────
with tab2:
    st.subheader("Track Event Ticket Prices")
    query       = st.text_input("Team or Artist", "Yankees")
    s_threshold = st.slider("Alert on % drop:", 5, 50, 10, key="sports_slider")

    if st.button("🔍 Find Tickets"):
        with st.spinner("Searching SeatGeek…"):
            try:
                url = "https://api.seatgeek.com/2/events?q=" + query + "&client_id=" + st.secrets["SG_CLIENT_ID"]
                r      = requests.get(url, timeout=15).json()
                events = r.get("events", [])
                st.session_state.sport_events = [
                    {"title": e["title"], "short_title": e["short_title"], "venue": e["venue"]["name"],
                     "date": e["datetime_local"][:10], "price": e["stats"].get("lowest_price"),
                     "event_id": e["id"], "threshold": s_threshold}
                    for e in events[:5] if e["stats"].get("lowest_price")
                ]
                if not st.session_state.sport_events:
                    st.warning("No events with prices found.")
            except KeyError:
                st.error("⚠️ SG_CLIENT_ID not found in Streamlit secrets.")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

    for i, e in enumerate(st.session_state.sport_events):
        with st.container(border=True):
            ca, cb = st.columns([3, 1])
            ca.write(f"**{e['title']}**")
            ca.caption(f"{e['venue']} | {e['date']}")
            cb.subheader(f"${e['price']}")
            if cb.button("Track Game", key=f"s_btn_{i}"):
                submit_track("Sports", e["short_title"], e["price"], e["threshold"], {"event_id": e["event_id"]})

# ── TAB 3: WATCHLIST ──────────────────────────────────────────────────────────
with tab3:
    st.subheader("📋 Your Active Watchlist")
    data = read_sheet()
    if data is None:
        st.info("Fix the connection error in the debug panel above.")
    elif data.empty:
        st.info("No items tracked yet. Add one from the Flights or Sports tabs.")
    else:
        st.dataframe(data[["DateStarted", "Category", "Item", "BasePrice", "Threshold", "Status"]], use_container_width=True)
        col_refresh, col_reset = st.columns([1, 4])
        if col_refresh.button("🔄 Refresh"):
            st.rerun()
        if col_reset.button("🗑️ Reset Tracking Tab"):
            if write_sheet(pd.DataFrame(columns=COLUMNS)):
                st.success("Tracking sheet cleared.")
                st.rerun()
