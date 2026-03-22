import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# 1. PAGE SETUP
st.set_page_config(page_title="Elite Price Agent", layout="wide", page_icon="🤖")

# 2. INITIALIZE GSHEETS CONNECTION
conn = st.connection("gsheets", type=GSheetsConnection)

# --- STURDIER LOGGING FUNCTION ---
def update_price_log(category, item, current_price):
    try:
        df = conn.read()
        if df is None or df.empty or 'Category' not in df.columns:
            df = pd.DataFrame(columns=["Date", "Category", "Item", "Price"])
        
        item_history = df[(df['Category'] == category) & (df['Item'] == item)]
        last_price = item_history.iloc[-1]['Price'] if not item_history.empty else None
        
        if last_price is None or float(current_price) != float(last_price):
            new_row = pd.DataFrame([{
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Category": category,
                "Item": item,
                "Price": float(current_price)
            }])
            updated_df = pd.concat([df, new_row], ignore_index=True)
            conn.update(data=updated_df)
            st.toast(f"📈 Logged: {item} at ${current_price}", icon="✅")
        else:
            st.toast(f"😴 No change for {item}", icon="ℹ️")
    except Exception as e:
        st.error(f"GSheets Error: {e}")

# --- UI LAYOUT ---
st.title("🤖 My Personal Price Agent")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["✈️ Flights", "🏀 Sports", "📊 Price History"])

# --- TAB 1: FLIGHTS ---
with tab1:
    st.header("Search Top 3 Cheapest Flights")
    c_settings, c_dates = st.columns([1, 2])
    with c_settings:
        trip_type = st.radio("Trip Type", ["One-Way", "Round-Trip"], horizontal=True)
        cabin = st.selectbox("Cabin Class", ["economy", "premium_economy", "business", "first"])
    with c_dates:
        col_origin, col_dest = st.columns(2)
        origin = col_origin.text_input("From (IATA)", "JFK").upper().strip()
        dest = col_dest.text_input("To (IATA)", "LAX").upper().strip()
        dep_date = st.date_input("Departure", datetime.now() + timedelta(days=14))
        ret_date = st.date_input("Return", datetime.now() + timedelta(days=21))

    if st.button("🔍 Find Flight Deals"):
        with st.spinner("Searching Duffel..."):
            headers = {"Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}", "Duffel-Version": "v2", "Content-Type": "application/json"}
            slices = [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}]
            if trip_type == "Round-Trip":
                slices.append({"origin": dest, "destination": origin, "departure_date": str(ret_date)})
            
            payload = {"data": {"slices": slices, "passengers": [{"type": "adult"}], "cabin_class": cabin}}
            res = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
            
            if res.status_code == 201:
                offers = res.json()['data']['offers']
                if offers:
                    sorted_offers = sorted(offers, key=lambda x: float(x['total_amount']))[:3]
                    update_price_log("Flight", f"{origin}-{dest} ({cabin})", sorted_offers[0]['total_amount'])
                    for idx, offer in enumerate(sorted_offers):
                        with st.expander(f"Option {idx+1}: {offer['total_currency']} {offer['total_amount']}"):
                            for s in offer['slices']:
                                seg = s['segments'][0]
                                st.write(f"**{seg['marketing_carrier']['name']}** - {seg['departing_at'][:16].replace('T', ' ')}")
                else: st.warning("No offers found.")
            else: st.error("Duffel Connection Error.")

# --- TAB 2: SPORTS (UPDATED SPECIFIC GAME LOGIC) ---
with tab2:
    st.header("Specific Game Ticket Tracker")
    col1, col2 = st.columns(2)
    with col1:
        team_query = st.text_input("Team/Event Name", "Lakers")
    with col2:
        search_after = st.date_input("Show games after:", datetime.now().date())

    if st.button("🔍 Find Upcoming Games"):
        with st.spinner(f"Searching SeatGeek..."):
            sg_id = st.secrets["SG_CLIENT_ID"]
            url = f"https://api.seatgeek.com/2/events?q={team_query}&datetime_utc.gt={search_after}&per_page=10&client_id={sg_id}"
            response = requests.get(url)
            if response.status_code == 200:
                st.session_state['found_games'] = response.json().get('events', [])
            else: st.error("SeatGeek Connection Error.")

    if 'found_games' in st.session_state and st.session_state['found_games']:
        game_options = {f"{e['title']} ({e['datetime_local'][:10]})": e for e in st.session_state['found_games']}
        selected_name = st.selectbox("Which game do you want to track?", list(game_options.keys()))
        
        if st.button("📈 Log Price for This Game"):
            event = game_options[selected_name]
            price = event['stats'].get('lowest_price')
            if price:
                st.metric(label=selected_name, value=f"${price}")
                update_price_log("Sports", selected_name, price)
            else: st.warning("No live pricing for this game yet.")

# --- TAB 3: HISTORY ---
with tab3:
    st.header("📈 Price Trends")
    try:
        df = conn.read()
        if df is not None and not df.empty:
            item = st.selectbox("Select Item", df['Item'].unique())
            plot_df = df[df['Item'] == item].copy()
            plot_df['Date'] = pd.to_datetime(plot_df['Date'])
            st.line_chart(plot_df.set_index('Date')['Price'])
            st.dataframe(plot_df.sort_values("Date", ascending=False), use_container_width=True)
        else: st.info("No data logged yet.")
    except: st.write("Waiting for first data entry...")

st.sidebar.info(f"Agent Active | {datetime.now().strftime('%H:%M')}")
