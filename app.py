import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# 1. PAGE SETUP
st.set_page_config(page_title="Elite Price Agent", layout="wide", page_icon="🕵️")

# 2. GSHEETS CONNECTION
# Note: Ensure [connections.gsheets] is in your Streamlit Cloud Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

def submit_track(category, item, current_price, threshold, metadata):
    status_placeholder = st.empty()
    status_placeholder.info("⏳ Connecting to Google Sheets...")
    
    try:
        # Step A: Force a fresh read of the Tracking tab
        try:
            df = conn.read(worksheet="Tracking", ttl=0)
        except Exception:
            # Create headers if tab is missing/empty
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
            
        conn.update(worksheet="Tracking", data=updated_df)
        
        # Step D: Clear Cache & Success UI
        st.cache_data.clear() 
        status_placeholder.empty()
        st.balloons()
        st.success(f"🎯 Successfully tracking: {item}")
        
    except Exception as e:
        status_placeholder.empty()
        st.error(f"❌ GSHEETS ERROR: {e}")
        st.info("Check: 1. Is 'Tracking' tab name exact? 2. Is the Sheet shared as 'Editor' to Anyone with link?")
        st.stop() 

# --- UI LAYOUT ---
st.title("🕵️ Elite Price Intelligence Agent")
st.caption("Live Price Tracking for Flight Routes & Sports Events")

tab1, tab2, tab3 = st.tabs(["✈️ Flights", "🏀 Sports", "📋 Watchlist"])

# --- TAB 1: FLIGHTS (Route-Based) ---
with tab1:
    st.subheader("Track a Flight Route")
    c1, c2, c3 = st.columns(3)
    with c1:
        origin = st.text_input("From (IATA Code)", "JFK").upper().strip()
        trip_type = st.selectbox("Trip Type", ["One-way", "Round-trip"])
    with c2:
        dest = st.text_input("To (IATA Code)", "LAX").upper().strip()
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
                            col_a.caption(f"Cabin: {cabin.title()} | Today's Low: **${price}**")
                            
                            if col_b.button(f"Track Route @ ${price}", key=f"f_btn_{i}"):
                                meta = {
                                    "origin": origin, "dest": dest, "date": str(dep_date), 
                                    "return": str(ret_date), "cabin": cabin, "type": trip_type
                                }
                                submit_track("Flight", f"{origin}-{dest} ({cabin})", price, f_threshold, meta)
                else:
                    st.warning("No flights found.")
            else:
                st.error(f"API Error {res.status_code}. Verify IATA codes and Secrets.")

# --- TAB 2: SPORTS ---
with tab2:
    st.subheader("Track Event Ticket Prices")
    query = st.text_input("Team or Artist", "Knicks")
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
        else:
            st.info("No events found.")

# --- TAB 3: WATCHLIST ---
with tab3:
    st.subheader("📋 Your Active Watchlist")
    try:
        # Fresh read for the watchlist
        data = conn.read(worksheet="Tracking", ttl=0)
        if data is not None and not data.empty:
            active_only = data[data['Status'] == 'Active']
            if not active_only.empty:
                st.dataframe(active_only[["DateStarted", "Category", "Item", "BasePrice", "Threshold"]], use_container_width=True)
                
                if st.button("🗑️ Reset Tracking Tab"):
                    # Keeps headers but wipes rows
                    empty_df = pd.DataFrame(columns=data.columns)
                    conn.update(worksheet="Tracking", data=empty_df)
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.write("No active tracks found.")
        else:
            st.write("Watchlist is currently empty.")
    except:
        st.info("Start tracking an item to see it appear here!")
