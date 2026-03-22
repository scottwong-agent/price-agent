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
        # Read existing data
        df = conn.read()
        
        # If the sheet is empty or malformed, initialize it
        if df is None or df.empty or 'Category' not in df.columns:
            df = pd.DataFrame(columns=["Date", "Category", "Item", "Price"])
        
        # Filter for this specific item to find the last price recorded
        item_history = df[(df['Category'] == category) & (df['Item'] == item)]
        
        last_price = None
        if not item_history.empty:
            last_price = item_history.iloc[-1]['Price']
        
        # Only log if price changed or it's a brand new item
        if last_price is None or float(current_price) != float(last_price):
            new_row = pd.DataFrame([{
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Category": category,
                "Item": item,
                "Price": float(current_price)
            }])
            updated_df = pd.concat([df, new_row], ignore_index=True)
            conn.update(data=updated_df)
            st.toast(f"📈 Logged New Price for {item}: ${current_price}", icon="✅")
        else:
            st.toast(f"😴 Price for {item} remains ${current_price}. No log added.", icon="ℹ️")
            
    except Exception as e:
        st.error(f"GSheets Logging Error: {e}")

# --- UI LAYOUT ---
st.title("🤖 My Personal Price Agent")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["✈️ Flights", "🏀 Sports", "📊 Price History"])

# --- TAB 1: FLIGHTS (DUFFEL API) ---
with tab1:
    st.header("Search Top 3 Cheapest Flights")
    c_settings, c_dates = st.columns([1, 2])
    
    with c_settings:
        trip_type = st.radio("Trip Type", ["One-Way", "Round-Trip"], horizontal=True)
        cabin = st.selectbox("Cabin Class", ["economy", "premium_economy", "business", "first"])
    
    with c_dates:
        col_origin, col_dest = st.columns(2)
        origin = col_origin.text_input("From (IATA Code)", "JFK").upper().strip()
        dest = col_dest.text_input("To (IATA Code)", "LAX").upper().strip()
        dep_date = st.date_input("Departure", datetime.now() + timedelta(days=14))
        ret_date = st.date_input("Return", datetime.now() + timedelta(days=21))

    if st.button("🔍 Find Best Flight Deals"):
        with st.spinner("Searching Duffel for the best prices..."):
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
                    # Sort by price and take top 3
                    sorted_offers = sorted(offers, key=lambda x: float(x['total_amount']))[:3]
                    
                    # Log the #1 cheapest result
                    best_price = sorted_offers[0]['total_amount']
                    flight_label = f"{origin}-{dest} ({cabin})"
                    update_price_log("Flight", flight_label, best_price)

                    # Display Top 3
                    for idx, offer in enumerate(sorted_offers):
                        with st.expander(f"Option {idx+1}: {offer['total_currency']} {offer['total_amount']}", expanded=(idx==0)):
                            for i, s in enumerate(offer['slices']):
                                leg = "🛫 Outbound" if i == 0 else "🛬 Return"
                                seg = s['segments'][0]
                                carrier = seg['marketing_carrier']['name']
                                flight_no = f"{seg['marketing_carrier']['iata_code']}{seg['marketing_carrier_flight_number']}"
                                dep_time = seg['departing_at'].replace('T', ' ')[:16]
                                st.write(f"**{leg}:** {carrier} ({flight_no}) at {dep_time}")
                else:
                    st.warning("No flight offers found for these dates.")
            else:
                st.error(f"Duffel Error: {res.json().get('errors', [{'message': 'Unknown error'}])[0]['message']}")

# --- TAB 2: SPORTS (SEATGEEK API) ---
with tab2:
    st.header("Sports Ticket Tracker")
    team = st.text_input("Enter Team Name", "Lakers")
    
    if st.button("Check Game Prices"):
        with st.spinner(f"Checking SeatGeek for {team} tickets..."):
            client_id = st.secrets["SG_CLIENT_ID"]
            url = f"https://api.seatgeek.com/2/events?q={team}&client_id={client_id}"
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('events'):
                    event = data['events'][0]
                    price = event['stats'].get('lowest_price')
                    
                    if price:
                        st.metric(label=f"Next Event: {event['title']}", value=f"${price}")
                        update_price_log("Sports", team, price)
                    else:
                        st.info("Event found, but no live pricing is currently available.")
                else:
                    st.warning("No upcoming events found for that team.")
            else:
                st.error("Could not connect to SeatGeek.")

# --- TAB 3: PRICE HISTORY (GSHEETS) ---
with tab3:
    st.header("📈 Price History Trends")
    try:
        history_df = conn.read()
        if history_df is not None and not history_df.empty and 'Item' in history_df.columns:
            # Dropdown to select which item to view
            unique_items = history_df['Item'].unique()
            selected_item = st.selectbox("Select a Saved Item to View History", unique_items)
            
            # Filter and Plot
            plot_data = history_df[history_df['Item'] == selected_item].copy()
            plot_data['Date'] = pd.to_datetime(plot_data['Date'])
            
            st.subheader(f"Price Trend for {selected_item}")
            st.line_chart(plot_data.set_index('Date')['Price'])
            
            st.subheader("Raw Log Data")
            st.dataframe(plot_data.sort_values(by="Date", ascending=False), use_container_width=True)
        else:
            st.info("No data has been logged to your Google Sheet yet. Perform a search to begin tracking!")
    except Exception as e:
        st.error(f"Could not load history from GSheets: {e}")

# Sidebar Info
st.sidebar.title("Agent Status")
st.sidebar.info("Connected to Duffel, SeatGeek, and Google Sheets.")
st.sidebar.write(f"Local time: {datetime.now().strftime('%H:%M:%S')}")
