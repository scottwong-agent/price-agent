import streamlit as st
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="Price Agent", layout="wide")
st.title("🤖 Elite Price Agent")

tab1, tab2 = st.tabs(["✈️ Flights", "🏀 Sports"])

with tab1:
    st.header("Search Flights")
    
    # Settings moved from sidebar to here
    col_settings, col_dates = st.columns([1, 2])
    with col_settings:
        trip_type = st.radio("Trip Type", ["One-Way", "Round-Trip"], horizontal=True)
        cabin = st.selectbox("Cabin Class", ["economy", "premium_economy", "business", "first"])
    
    with col_dates:
        col_origin, col_dest = st.columns(2)
        origin = col_origin.text_input("From (IATA)", "JFK").upper().strip()
        dest = col_dest.text_input("To (IATA)", "LAX").upper().strip()
        
        col_d1, col_d2 = st.columns(2)
        dep_date = col_d1.date_input("Departure", datetime.now() + timedelta(days=14))
        ret_date = col_d2.date_input("Return", datetime.now() + timedelta(days=21))

    if st.button("🔍 Find Best Deal"):
        headers = {
            "Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}",
            "Duffel-Version": "v2",
            "Content-Type": "application/json"
        }

        slices = [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}]
        if trip_type == "Round-Trip":
            slices.append({"origin": dest, "destination": origin, "departure_date": str(ret_date)})

        payload = {"data": {"slices": slices, "passengers": [{"type": "adult"}], "cabin_class": cabin}}

        response = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
        
        if response.status_code == 201:
            offers = response.json()['data']['offers']
            if offers:
                # Sort by price and take the best one
                best = min(offers, key=lambda x: float(x['total_amount']))
                
                st.divider()
                st.subheader(f"✅ Best Match: {best['total_currency']} {best['total_amount']}")
                
                # Digging into the slices to get flight info
                for i, s in enumerate(best['slices']):
                    direction = "Departure" if i == 0 else "Return"
                    st.write(f"**{direction} Flight:**")
                    
                    for segment in s['segments']:
                        airline = segment['marketing_carrier']['name']
                        flight_no = f"{segment['marketing_carrier_flight_number']}"
                        dep_time = segment['departing_at'].replace('T', ' ')[:16]
                        arr_time = segment['arriving_at'].replace('T', ' ')[:16]
                        
                        st.info(f"✈️ **{airline}** (Flight #{flight_no})  \n"
                                f"🛫 Leaves: {dep_time}  \n"
                                f"🛬 Arrives: {arr_time}")
            else:
                st.warning("No flights found for these specific criteria.")
        else:
            st.error(f"Error: {response.json()['errors'][0]['message']}")

with tab2:
    st.header("Sports Tracker")
    st.write("SeatGeek integration goes here...")
