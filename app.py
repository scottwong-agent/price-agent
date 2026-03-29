import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# 1. PAGE SETUP
st.set_page_config(page_title="Elite Price Agent", layout="wide", page_icon="🕵️")

# 2. GSHEETS CONNECTION
conn = st.connection("gsheets", type=GSheetsConnection)

def submit_track(category, item, current_price, threshold, metadata):
    status_placeholder = st.empty()
    status_placeholder.info("⏳ Connecting to Google Sheets...")
    
    try:
        # DEBUG: Check if function even starts
        st.write(f"DEBUG: Attempting to save {item}...") 

        try:
            # Read fresh data from the 'Tracking' tab
            df = conn.read(worksheet="Tracking", ttl=0)
        except Exception as read_e:
            # DEBUG: Show if the tab 'Tracking' isn't found
            st.error(f"READ ERROR: {read_e}. Ensure your tab is named exactly 'Tracking'.")
            df = pd.DataFrame(columns=["DateStarted", "Category", "Item", "BasePrice", "Threshold", "Metadata", "Status"])
        
        # Step B: Prepare the new row
        new_row = pd.DataFrame([{
            "DateStarted": datetime.now().strftime("%Y-%m-%d"),
            "Category": category,
            "Item": item,
            "BasePrice": float(current_price),
            "Threshold": int(threshold),
            "Metadata": str(metadata),
            "Status": "Active"
        }])
        
        # Step C: Append and push
        if df is not None and not df.empty:
            updated_df = pd.concat([df, new_row], ignore_index=True)
        else:
            updated_df = new_row
            
        # Push to Google Sheets
        conn.update(worksheet="Tracking", data=updated_df)
        
        # Step D: Clear Cache & Success UI
        st.cache_data.clear() 
        status_placeholder.empty()
        st.balloons()
        st.success(f"🎯 Successfully tracking: {item}")
        
    except Exception as e:
        status_placeholder.empty()
        # DEBUG: The specific reason the "Save" failed
        st.error(f"❌ GSHEETS UPDATE ERROR: {e}")
        st.info("Check: 1. Is 'Tracking' tab name exact? 2. Is the Sheet shared as 'Editor' with the Service Account?")
        st.stop() 

# --- UI LAYOUT ---
st.title("🕵️ Elite Price Intelligence Agent")
st.caption("Live Price Tracking for Flight Routes & Sports Events")

tab1, tab2, tab3 = st.tabs(["✈️ Flights", "🏀 Sports", "📋 Watchlist"])

# --- TAB 1: FLIGHTS ---
with tab1:
    st.subheader("Track a Flight Route")
    c1, c2, c3 = st.columns(3)
    with c1:
        origin = st.text_input("From (IATA)", "SFO").upper().strip()
        trip_type = st.selectbox("Trip Type", ["One-way", "Round-trip"])
    with c2:
        dest = st.text_input("To (IATA)", "JFK").upper().strip()
        cabin = st.selectbox("Cabin Class", ["economy", "premium_economy", "business", "first"])
    with c3:
        dep_date = st.date_input("Departure Date", datetime.now() + timedelta(days=30))
        ret_date = None
        if trip_type == "Round-trip":
            ret_date = st.date_input("Return Date", datetime.now() + timedelta(days=37))

    f_threshold = st.slider("Alert me if price drops by %:", 5, 50, 10, key="flight_slider")

    if st.button("🔍 Find Cheapest Deals"):
        with st.spinner("Searching Duffel..."):
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
                        price = offer['total_amount']
                        airline = offer['slices'][0]['segments'][0]['operating_carrier']['name']
                        
                        with st.container(border=True):
                            col_a, col_b = st.columns([3, 1])
                            col_a.write(f"**{airline}** | {origin} ➔ {dest}")
                            col_a.caption(f"Price: **${price}**")
                            
                            if col_b.button(f"Track @ ${price}", key=f"f_btn_{i}"):
                                meta = {"origin": origin, "dest": dest, "date": str(dep_date), "cabin": cabin}
                                submit_track("Flight", f"{origin}-{dest}", price, f_threshold, meta)
                else:
                    st.warning("No flights found.")

# --- TAB 2: SPORTS ---
with tab2:
    st.subheader("Track Event Ticket Prices")
    query = st.text_input("Team or Artist", "Yankees")
    s_threshold = st.slider("Alert on % drop:", 5, 50, 10, key="sports_slider")

    if st.button("🔍 Find Tickets"):
        url = f"https://api.seatgeek.com/2/events?q={query}&client_id={st.secrets['SG_CLIENT_ID']}"
        r = requests.get(url).json()
        events = r.get('events', [])
        
        if events:
            for i, e in enumerate(events[:5]):
                price = e['stats'].get('lowest_price')
                if price:
                    with st.container(border=True):
                        ca, cb = st.columns([3, 1])
                        ca.write(f"**{e['title']}**")
                        ca.caption(f"{e['venue']['name']} | {e['datetime_local'][:10]}")
                        cb.subheader(f"${price}")
                        if cb.button("Track Game", key=f"s_btn_{i}"):
                            submit_track("Sports", e['short_title'], price, s_threshold, {"event_id": e['id']})

# --- TAB 3: WATCHLIST ---
with tab3:
    st.subheader("📋 Your Active Watchlist")
    try:
        data = conn.read(worksheet="Tracking", ttl=0)
        if data is not None and not data.empty:
            st.dataframe(data[["DateStarted", "Category", "Item", "BasePrice", "Threshold", "Status"]], use_container_width=True)
            if st.button("🗑️ Reset Tracking Tab"):
                empty_df = pd.DataFrame(columns=data.columns)
                conn.update(worksheet="Tracking", data=empty_df)
                st.cache_data.clear()
                st.rerun()
        else:
            st.write("Watchlist is empty.")
    except:
        st.info("Start tracking an item to see it appear here!")
