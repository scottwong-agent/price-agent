import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# 1. PAGE SETUP
st.set_page_config(page_title="Elite Price Agent", layout="wide", page_icon="🕵️")

# 2. INITIALIZE GSHEETS CONNECTION
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNCTION: SUBMIT TRACKING REQUEST ---
def submit_track(category, item, current_price, drop_threshold, metadata):
    try:
        df = conn.read(worksheet="Tracking")
        if df is None or df.empty:
            df = pd.DataFrame(columns=["DateStarted", "Category", "Item", "BasePrice", "Threshold", "Metadata", "Status"])
        
        new_entry = pd.DataFrame([{
            "DateStarted": datetime.now().strftime("%Y-%m-%d"),
            "Category": category,
            "Item": item,
            "BasePrice": float(current_price),
            "Threshold": int(drop_threshold),
            "Metadata": str(metadata),
            "Status": "Active"
        }])
        
        updated_df = pd.concat([df, new_entry], ignore_index=True)
        conn.update(worksheet="Tracking", data=updated_df)
        st.toast(f"🎯 Tracking started for {item}!", icon="✅")
    except Exception as e:
        st.error(f"Error saving to Tracking sheet: {e}")

# --- UI LAYOUT ---
st.title("🕵️ Elite Price Intelligence Agent")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["✈️ Search Flights", "🏀 Search Sports", "📋 Active Watchlist"])

# --- TAB 1: FLIGHTS (NEW & IMPROVED) ---
with tab1:
    st.header("Find a Flight to Track")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        origin = st.text_input("From (IATA Code)", "JFK").upper().strip()
        trip_type = st.selectbox("Trip Type", ["One-way", "Round-trip"])
    with col2:
        dest = st.text_input("To (IATA Code)", "LAX").upper().strip()
        cabin = st.selectbox("Cabin Class", ["economy", "premium_economy", "business", "first"])
    with col3:
        dep_date = st.date_input("Departure Date", datetime.now() + timedelta(days=30))
        ret_date = None
        if trip_type == "Round-trip":
            ret_date = st.date_input("Return Date", datetime.now() + timedelta(days=37))

    f_threshold = st.slider("Alert me if price drops by X%:", 5, 50, 10)

    if st.button("🔍 Search Best Deals"):
        with st.spinner("Searching Duffel..."):
            headers = {
                "Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}",
                "Duffel-Version": "v2",
                "Content-Type": "application/json"
            }
            
            slices = [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}]
            if trip_type == "Round-trip" and ret_date:
                slices.append({"origin": dest, "destination": origin, "departure_date": str(ret_date)})

            payload = {
                "data": {
                    "slices": slices, 
                    "passengers": [{"type": "adult"}], 
                    "cabin_class": cabin
                }
            }
            
            res = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
            
            if res.status_code == 201:
                offers = res.json()['data']['offers']
                if offers:
                    # Sort by price and take top 3
                    sorted_offers = sorted(offers, key=lambda x: float(x['total_amount']))[:3]
                    
                    st.subheader("🏆 Top 3 Lowest Prices Found")
                    for i, offer in enumerate(sorted_offers):
                        price = float(offer['total_amount'])
                        # Get details from the first segment
                        seg = offer['slices'][0]['segments'][0]
                        airline = seg['operating_carrier']['name']
                        flight_no = f"{seg['operating_carrier']['iata_code']}{seg['operating_carrier_flight_number']}"
                        
                        with st.container(border=True):
                            c_left, c_mid, c_right = st.columns([2, 2, 1])
                            c_left.write(f"**{airline}**")
                            c_left.caption(f"Flight: {flight_no} | Class: {cabin.title()}")
                            c_mid.write(f"📅 {dep_date}")
                            if ret_date: c_mid.write(f"🔙 {ret_date}")
                            c_right.subheader(f"${price}")
                            
                            if c_right.button(f"Track This", key=f"f_btn_{i}"):
                                meta = {
                                    "origin": origin, "dest": dest, "date": str(dep_date), 
                                    "return": str(ret_date), "cabin": cabin, "type": trip_type
                                }
                                submit_track("Flight", f"{airline} ({origin}-{dest})", price, f_threshold, meta)
                else:
                    st.warning("No flights found for those dates.")
            else:
                st.error("Duffel API Error. Check your IATA codes.")

# --- TAB 2: SPORTS ---
with tab2:
    st.header("Find a Game to Track")
    team = st.text_input("Team/Event Name", "Lakers")
    s_threshold = st.slider("Alert me if price drops by X%:", 5, 50, 10, key="s_thresh")
    
    if st.button("🔍 Search Games"):
        url = f"https://api.seatgeek.com/2/events?q={team}&client_id={st.secrets['SG_CLIENT_ID']}"
        r = requests.get(url).json()
        st.session_state['found_games'] = r.get('events', [])

    if 'found_games' in st.session_state and st.session_state['found_games']:
        for i, g in enumerate(st.session_state['found_games'][:5]):
            price = g['stats'].get('lowest_price')
            if price:
                with st.container(border=True):
                    col_a, col_b = st.columns([3, 1])
                    col_a.write(f"**{g['title']}**")
                    col_a.caption(f"Venue: {g['venue']['name']} | Date: {g['datetime_local'][:10]}")
                    col_b.subheader(f"${price}")
                    if col_b.button("Track Game", key=f"s_btn_{i}"):
                        meta = {"event_id": g['id']}
                        submit_track("Sports", g['short_title'], price, s_threshold, meta)

# --- TAB 3: WATCHLIST ---
with tab3:
    st.header("📋 Your Active Watchlist")
    try:
        tracks = conn.read(worksheet="Tracking")
        if tracks is not None and not tracks.empty:
            active = tracks[tracks['Status'] == 'Active']
            if active.empty:
                st.info("No active tracks.")
            else:
                st.dataframe(active[['Category', 'Item', 'BasePrice', 'Threshold']])
                if st.button("Clear All Stopped Tracks"):
                    # Maintenance option
                    cleaned = tracks[tracks['Status'] == 'Active']
                    conn.update(worksheet="Tracking", data=cleaned)
                    st.rerun()
        else:
            st.info("Watchlist is empty.")
    except:
        st.warning("Create a 'Tracking' tab in your Google Sheet to see this.")
