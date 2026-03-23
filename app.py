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
        # Read the 'Tracking' worksheet specifically
        df = conn.read(worksheet="Tracking")
        
        if df is None or df.empty or 'Status' not in df.columns:
            df = pd.DataFrame(columns=["DateStarted", "Category", "Item", "BasePrice", "Threshold", "Metadata", "Status"])
        
        new_entry = pd.DataFrame([{
            "DateStarted": datetime.now().strftime("%Y-%m-%d"),
            "Category": category,
            "Item": item,
            "BasePrice": float(current_price),
            "Threshold": int(drop_threshold),
            "Metadata": str(metadata), # Stores API IDs for the daily bot to use
            "Status": "Active"
        }])
        
        updated_df = pd.concat([df, new_entry], ignore_index=True)
        conn.update(worksheet="Tracking", data=updated_df)
        st.toast(f"🎯 Tracking started for {item}!", icon="✅")
    except Exception as e:
        st.error(f"Error saving to Tracking sheet: {e}. Ensure you have a 'Tracking' tab in GSheets.")

# --- UI LAYOUT ---
st.title("🕵️ Elite Price Intelligence Agent")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["✈️ Search Flights", "🏀 Search Sports", "📋 Active Watchlist"])

# --- TAB 1: FLIGHTS ---
with tab1:
    st.header("Find a Flight to Track")
    c1, c2 = st.columns(2)
    with c1:
        origin = st.text_input("Origin (IATA)", "JFK").upper().strip()
        dest = st.text_input("Destination (IATA)", "LAX").upper().strip()
    with c2:
        dep_date = st.date_input("Departure Date", datetime.now() + timedelta(days=30))
        threshold = st.slider("Alert me if price drops by X%:", 5, 50, 10, key="f_thresh")

    if st.button("🔍 Search & Preview"):
        with st.spinner("Searching Duffel..."):
            headers = {"Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}", "Duffel-Version": "v2", "Content-Type": "application/json"}
            payload = {"data": {"slices": [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}], "passengers": [{"type": "adult"}], "cabin_class": "economy"}}
            res = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
            
            if res.status_code == 201:
                offers = res.json()['data']['offers']
                if offers:
                    best = sorted(offers, key=lambda x: float(x['total_amount']))[0]
                    price = float(best['total_amount'])
                    st.metric("Current Best Price", f"${price}")
                    
                    if st.button(f"🚀 Start Daily Tracking at ${price}"):
                        meta = {"origin": origin, "dest": dest, "date": str(dep_date)}
                        submit_track("Flight", f"{origin}-{dest} Flight", price, threshold, meta)
                else: st.warning("No flights found.")
            else: st.error("Duffel API Connection Error.")

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
        game_map = {f"{g['title']} ({g['datetime_local'][:10]})": g for g in st.session_state['found_games']}
        selected = st.selectbox("Select the exact game:", list(game_map.keys()))
        
        if st.button("📌 Start Daily Tracking"):
            g = game_map[selected]
            price = g['stats'].get('lowest_price') or g['stats'].get('average_price')
            if price:
                meta = {"event_id": g['id']}
                submit_track("Sports", selected, price, s_threshold, meta)
            else: st.error("Cannot track: No price data available for this game.")

# --- TAB 3: ACTIVE TRACKS & STOPPING ---
with tab3:
    st.header("📋 Your Active Watchlist")
    try:
        tracks = conn.read(worksheet="Tracking")
        if tracks is not None and not tracks.empty:
            # Only show Active tracks
            active_tracks = tracks[tracks['Status'] == 'Active']
            
            if active_tracks.empty:
                st.info("No active tracks found.")
            else:
                for i, row in active_tracks.iterrows():
                    with st.container():
                        c1, c2, c3 = st.columns([3, 1, 1])
                        c1.write(f"**{row['Item']}**")
                        c1.caption(f"Started: {row['DateStarted']} | Base: ${row['BasePrice']} | Alert Threshold: -{row['Threshold']}%")
                        
                        if c2.button("🗑️ Stop Tracking", key=f"stop_{i}"):
                            tracks.at[i, 'Status'] = 'Stopped'
                            conn.update(worksheet="Tracking", data=tracks)
                            st.rerun()
        else:
            st.info("Your tracking sheet is empty. Start a search to add items!")
    except Exception as e:
        st.error(f"Could not load tracking data: {e}")

st.sidebar.markdown(f"**System Status:** Running  \n**Time:** {datetime.now().strftime('%H:%M:%S')}")
