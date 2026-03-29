import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# ─── PAGE SETUP ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Elite Price Agent", layout="wide", page_icon="🕵️")

# ─── SESSION STATE INIT ───────────────────────────────────────────────────────
# Results must live in session_state so they survive the rerun triggered
# when the user clicks a "Track" button inside the results list.
if "flight_offers" not in st.session_state:
    st.session_state.flight_offers = []
if "sport_events" not in st.session_state:
    st.session_state.sport_events = []

# ─── GSHEETS CONNECTION ───────────────────────────────────────────────────────
conn = st.connection("gsheets", type=GSheetsConnection)

COLUMNS = ["DateStarted", "Category", "Item", "BasePrice", "Threshold", "Metadata", "Status"]

def read_sheet():
    try:
        df = conn.read(worksheet="Tracking", ttl=0, usecols=COLUMNS)
        if df is None or df.empty:
            return pd.DataFrame(columns=COLUMNS)
        return df.dropna(how="all").reset_index(drop=True)
    except Exception as e:
        st.error(f"❌ READ ERROR: {e}")
        st.code(str(e), language=None)
        return None

def write_sheet(df):
    try:
        df = df[COLUMNS].reset_index(drop=True)
        conn.update(worksheet="Tracking", data=df)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ WRITE ERROR: {e}")
        st.code(str(e), language=None)
        st.caption(
            "Common causes:\n"
            "1. Service account not shared as **Editor** on the Google Sheet\n"
            "2. Tab not named exactly **Tracking**\n"
            "3. `spreadsheet` URL missing or wrong in Streamlit secrets"
        )
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
                    "Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}",
                    "Duffel-Version": "v2",
                    "Content-Type": "application/json",
                }
                slices = [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}]
                if trip_type == "Round-trip" and ret_date:
                    slices.append({"origin": dest, "destination": origin, "departure_date": str(ret_date)})

                payload = {
                    "data": {
                        "slices": slices,
                        "passengers": [{"type": "adult"}],
                        "cabin_class": cabin,
                    }
                }
                res = requests.post(
                    "https://api.duffel.com/air/offer_requests",
                    json=payload,
                    headers=headers,
                    timeout=30,
                )

                if res.status_code in (200, 201):
                    offers = res.json()["data"]["offers"]
                    # ── Store in session_state so Track buttons survive the rerun ──
                    st.session_state.flight_offers = [
                        {
                            "price":    o["total_amount"],
                            "airline":  o["slices"][0]["segments"][0]["operating_carrier"]["name"],
                            "origin":   origin,
                            "dest":     dest,
                            "dep_date": str(dep_date),
                            "cabin":    cabin,
                            "threshold": f_threshold,
                        }
                        for o in sorted(offers, key=lambda x: float(x["total_amount"]))[:3]
                    ]
                else:
                    st.error(f"Duffel API error {res.status_code}: {res.text[:300]}")
                    st.session_state.flight_offers = []

            except KeyError:
                st.error("⚠️ `DUFFEL_TOKEN` not found in Streamlit secrets.")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

    # ── Render stored flight results (persists across reruns) ──
    for i, offer in enumerate(st.session_state.flight_offers):
        with st.container(border=True):
            col_a, col_b = st.columns([3, 1])
            col_a.write(f"**{offer['airline']}** | {offer['origin']} ➔ {offer['dest']}")
            col_a.caption(f"Cabin: **{offer['cabin']}** | Date: {offer['dep_date']} | Price: **${offer['price']}**")
            if col_b.button(f"Track @ ${offer['price']}", key=f"f_btn_{i}"):
                meta = {
                    "origin": offer["origin"],
                    "dest":   offer["dest"],
                    "date":   offer["dep_date"],
                    "cabin":  offer["cabin"],
                }
                submit_track(
                    "Flight",
                    f"{offer['origin']}-{offer['dest']}",
                    offer["price"],
                    offer["threshold"],
                    meta,
                )

# ── TAB 2: SPORTS ─────────────────────────────────────────────────────────────
with tab2:
    st.subheader("Track Event Ticket Prices")
    query       = st.text_input("Team or Artist", "Yankees")
    s_threshold = st.slider("Alert on % drop:", 5, 50, 10, key="sports_slider")

    if st.button("🔍 Find Tickets"):
        with st.spinner("Searching SeatGeek…"):
            try:
                url = (
                    f"https://api.seatgeek.com/2/events"
                    f"?q={query}&client_id={st.secrets['SG_CLIENT_ID']}"
                )
                r      = requests.get(url, timeout=15).json()
                events = r.get("events", [])

                # ── Store in session_state so Track buttons survive the rerun ──
                st.session_state.sport_events = [
                    {
                        "title":      e["title"],
                        "short_title": e["short_title"],
                        "venue":      e["venue"]["name"],
                        "date":       e["datetime_local"][:10],
                        "price":      e["stats"].get("lowest_price"),
                        "event_id":   e["id"],
                        "threshold":  s_threshold,
                    }
                    for e in events[:5]
                    if e["stats"].get("lowest_price")
                ]

                if not st.session_state.sport_events:
                    st.warning("No events with prices found. Try a different search term.")

            except KeyError:
                st.error("⚠️ `SG_CLIENT_ID` not found in Streamlit secrets.")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

    # ── Render stored event results (persists across reruns) ──
    for i, e in enumerate(st.session_state.sport_events):
        with st.container(border=True):
            ca, cb = st.columns([3, 1])
            ca.write(f"**{e['title']}**")
            ca.caption(f"{e['venue']} | {e['date']}")
            cb.subheader(f"${e['price']}")
            if cb.button("Track Game", key=f"s_btn_{i}"):
                submit_track(
                    "Sports",
                    e["short_title"],
                    e["price"],
                    e["threshold"],
                    {"event_id": e["event_id"]},
                )

# ── TAB 3: WATCHLIST ──────────────────────────────────────────────────────────
with tab3:
    st.subheader("📋 Your Active Watchlist")

    data = read_sheet()

    if data is None:
        st.info("Fix the sheet connection error above, then refresh.")
    elif data.empty:
        st.info("No items tracked yet. Add one from the Flights or Sports tabs.")
    else:
        st.dataframe(
            data[["DateStarted", "Category", "Item", "BasePrice", "Threshold", "Status"]],
            use_container_width=True,
        )

        col_refresh, col_reset = st.columns([1, 4])
        if col_refresh.button("🔄 Refresh"):
            st.rerun()

        if col_reset.button("🗑️ Reset Tracking Tab"):
            empty_df = pd.DataFrame(columns=COLUMNS)
            if write_sheet(empty_df):
                st.success("Tracking sheet cleared.")
                st.rerun()
