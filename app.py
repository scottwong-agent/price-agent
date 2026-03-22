import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# 1. PAGE SETUP
st.set_page_config(page_title="Elite Price Agent", layout="wide", page_icon="🤖")

# 2. INITIALIZE GSHEETS CONNECTION
conn = st.connection("gsheets", type=GSheetsConnection)

# --- SMART LOGGING FUNCTION ---
def update_price_log(category, item, current_price):
    try:
        # Read existing data
        df = conn.read()
        
        # Filter for this specific item to find the last price
        item_history = df[(df['Category'] == category) & (df['Item'] == item)]
        
        last_price = None
        if not item_history.empty:
            last_price = item_history.iloc[-1]['Price']
        
        # Only log if price changed or first time tracking
        if last_price is None or float(current_price) != float(last_price):
            new_row = pd.DataFrame([{
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Category": category,
                "Item": item,
                "Price": float(current_price)
            }])
            updated_df = pd.concat([df, new_row], ignore_index=True)
            conn.update(data=updated_df)
            st.toast(f"📈 Price update for {item}: ${current_price}", icon="✅")
        else:
            st.toast(f"😴 No change for {item} (${current_price})", icon="ℹ️")
    except Exception as e:
        st.error(f"GSheets Log Error: {e}")

# --- UI LAYOUT ---
st.title("🤖 My Personal Price Agent")
tab1, tab2, tab3 = st.tabs(["✈️ Flights", "🏀 Sports", "📊 History"])

# --- TAB 1: FLIGHTS (DUFFEL) ---
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

    if st.button("🔍 Find Best Flight Deals"):
        headers = {
            "Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}",
            "Duffel-Version": "v2",
            "Content-Type": "application/json"
        }
        slices = [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}]
        if trip_type == "Round-Trip":
            slices.append({"origin": dest, "destination": origin, "departure_date": str(ret_date)})

        payload = {"data": {"slices": slices, "passengers": [{"type": "adult"}], "cabin_class": cabin}}
        
        res = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
        if res.status_code == 201:
            offers = res.json()['data']['offers']
            if offers:
                sorted_offers = sorted(offers, key=lambda x: float(x['total_amount']))[:3]
                
                # Log the #1 absolute cheapest price
                cheapest_price = sorted_offers[0]['total_amount']
                flight_label = f"{origin}-{dest} ({cabin})"
                update_price_log("Flight", flight_label, cheapest_price)

                for idx, offer in enumerate(sorted_offers):
                    with st.expander(f"Option {idx+1}: {offer['total_currency']} {offer['total_amount']}", expanded=(idx==0)):
                        for i, s in enumerate(offer['slices']):
                            leg = "🛫 Outbound" if i == 0 else "🛬 Return"
                            seg = s['segments'][0]
                            st.write(f"**{leg}:** {seg['marketing_carrier']['name']} ({seg['marketing_carrier']['iata_code']}{seg['marketing_carrier_flight_number']}) at {seg['departing_at'].replace('T', ' ')[:16]}")
            else:
                st.warning("No offers found.")
        else:
            st.error(f"Duffel Error: {res.json()['errors'][0]['message']}")

# --- TAB 2: SPORTS (SEATGEEK) ---
with tab2:
    st.header("Sports Ticket Tracker")
    team = st.text_input("Team Name", "Lakers")
    if st.button("Check Game Prices"):
        client_id = st.secrets["SG_CLIENT_ID"]
        url = f"https://api.seatgeek.com/2/events?q={team}&client_id={client_id}"
        data = requests.get(url).json()
        if data.get('events'):
            event = data['events'][0]
            price = event['stats'].get('lowest_price')
            if price:
                st.metric(label=event['title'], value=f"${price}")
                update_price_log("Sports", team, price)
            else:
                st.info("Event found, but no live pricing available.")
        else:
            st.warning("No events found.")

# --- TAB 3: PRICE HISTORY (GSHEETS) ---
with tab3:
    st.header("📈 Price History Trend")
    try:
        history_df = conn.read()
        if not history_df.empty:
            item_to_plot = st.selectbox("Select Item to View History", history_df['Item'].unique())
            plot_data = history_df[history_df['Item'] == item_to_plot]
            st.line_chart(plot_data.set_index('Date')['Price'])
            st.dataframe(plot_data)
        else:
            st.info("No data logged yet. Perform a search to start tracking!")
    except Exception as e:
        st.error("Could not load history.")

st.sidebar.write(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
