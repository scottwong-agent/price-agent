import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# 1. PAGE SETUP
st.set_page_config(page_title="Elite Price Agent", layout="wide", page_icon="🕵️")

# 2. GSHEETS CONNECTION
# Ensure you have st.secrets["connections"]["gsheets"] set up in Streamlit Cloud
conn = st.connection("gsheets", type=GSheetsConnection)

def submit_track(category, item, current_price, threshold, metadata):
    try:
        st.write("DEBUG: Attempting to connect to sheet...")
        df = conn.read(worksheet="Tracking")
        st.write("DEBUG: Sheet read successfully. Current rows:", len(df))
        
        new_row = pd.DataFrame([{
            "DateStarted": datetime.now().strftime("%Y-%m-%d"),
            "Category": category,
            "Item": item,
            "BasePrice": float(current_price),
            "Threshold": int(threshold),
            "Metadata": str(metadata),
            "Status": "Active"
        }])
        
        updated_df = pd.concat([df, new_row], ignore_index=True)
        conn.update(worksheet="Tracking", data=updated_df)
        st.balloons() # This will be very obvious if it works!
        st.success("SUCCESS!")
    except Exception as e:
        st.error(f"DETAILED ERROR: {e}")
        st.exception(e) # This will show the full technical traceback

# --- UI ---
st.title("🕵️ Elite Price Intelligence Agent")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["✈️ Flights", "🏀 Sports", "📋 Watchlist"])

# --- TAB 1: FLIGHTS (Route Tracking) ---
with tab1:
    st.header("Track a Flight Route")
    c1, c2, c3 = st.columns(3)
    with c1:
        origin = st.text_input("From (IATA)", "JFK").upper().strip()
        trip_type = st.selectbox("Trip Type", ["One-way", "Round-trip"])
    with c2:
        dest = st.text_input("To (IATA)", "LAX").upper().strip()
        cabin = st.selectbox("Class", ["economy", "premium_economy", "business", "first"])
    with c3:
        dep_date = st.date_input("Departure", datetime.now() + timedelta(days=30))
        ret_date = st.date_input("Return", datetime.now() + timedelta(days=37)) if trip_type == "Round-trip" else None

    f_threshold = st.slider("Alert me if price drops by %:", 5, 50, 10)

    if st.button("🔍 Find Cheapest in Route"):
        with st.spinner("Scanning all airlines..."):
            headers = {
                "Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}",
                "Duffel-Version": "v2",
                "Content-Type": "application/json"
            }
            slices = [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}]
            if trip_type == "Round-trip" and ret_date:
                slices.append({"origin": dest, "destination": origin, "departure_date": str(ret_date)})

            payload = {"data": {"slices": slices, "passengers": [{"type": "adult"}], "cabin_class": cabin}}
            res = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
            
            if res.status_code == 201:
                offers = res.json()['data']['offers']
                if offers:
                    sorted_offers = sorted(offers, key=lambda x: float(x['total_amount']))[:3]
                    for i, offer in enumerate(sorted_offers):
                        with st.container(border=True):
                            col_a, col_b = st.columns([3, 1])
                            carrier = offer['slices'][0]['segments'][0]['operating_carrier']['name']
                            price = offer['total_amount']
                            col_a.write(f"**{carrier}** | {origin} ➔ {dest}")
                            col_a.caption(f"Class: {cabin.title()} | Total: ${price}")
                            if col_b.button(f"Track Route @ ${price}", key=f"f_{i}"):
                                meta = {"origin": origin, "dest": dest, "date": str(dep_date), "return": str(ret_date), "cabin": cabin, "type": trip_type}
                                submit_track("Flight", f"{origin}-{dest} ({cabin})", price, f_threshold, meta)
                else: st.warning("No flights found.")
            else: st.error("Check your IATA codes or API Token.")

# --- TAB 2: SPORTS ---
with tab2:
    st.header("Track Sports & Events")
    query = st.text_input("Search Team or Artist", "Knicks")
    s_threshold = st.slider("Alert on % drop:", 5, 50, 10, key="s_slider")

    if st.button("🔍 Find Events"):
        url = f"https://api.seatgeek.com/2/events?q={query}&client_id={st.secrets['SG_CLIENT_ID']}"
        data = requests.get(url).json()
        events = data.get('events', [])
        
        if events:
            for i, e in enumerate(events[:5]):
                low_price = e['stats'].get('lowest_price')
                if low_price:
                    with st.container(border=True):
                        ca, cb = st.columns([3, 1])
                        ca.write(f"**{e['title']}**")
                        ca.caption(f"{e['venue']['name']} | {e['datetime_local'][:10]}")
                        cb.subheader(f"${low_price}")
                        if cb.button("Track Event", key=f"s_{i}"):
                            submit_track("Sports", e['short_title'], low_price, s_threshold, {"event_id": e['id']})
        else: st.info("No upcoming events found.")

# --- TAB 3: WATCHLIST ---
with tab3:
    st.header("📋 Current Watchlist")
    try:
        data = conn.read(worksheet="Tracking")
        if not data.empty:
            active = data[data['Status'] == 'Active']
            st.dataframe(active[["DateStarted", "Category", "Item", "BasePrice", "Threshold"]], use_container_width=True)
            if st.button("🗑️ Clear Stopped Tracks"):
                conn.update(worksheet="Tracking", data=active)
                st.rerun()
        else: st.write("Your watchlist is empty.")
    except: st.error("Ensure your Google Sheet has a 'Tracking' tab.")
