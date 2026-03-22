import streamlit as st
import requests
from datetime import datetime, timedelta

st.title("🤖 Elite Travel & Sports Agent")

# --- INPUTS ---
with st.sidebar:
    st.header("Settings")
    trip_type = st.radio("Trip Type", ["One-Way", "Round-Trip"])
    cabin = st.selectbox("Cabin Class", ["economy", "premium_economy", "business", "first"])

tab1, tab2 = st.tabs(["✈️ Flights", "🏀 Sports"])

with tab1:
    col1, col2 = st.columns(2)
    origin = col1.text_input("From (IATA)", "JFK")
    dest = col2.text_input("To (IATA)", "LAX")
    
    dep_date = st.date_input("Departure", datetime.now() + timedelta(days=14))
    ret_date = None
    if trip_type == "Round-Trip":
        ret_date = st.date_input("Return", datetime.now() + timedelta(days=21))

    if st.button("Search Best Flights"):
        headers = {
            "Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}",
            "Duffel-Version": "v2", # Use v2 for 2026 stability
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Build the 'slices' (Duffel's term for trip legs)
        slices = [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}]
        if trip_type == "Round-Trip" and ret_date:
            slices.append({"origin": dest, "destination": origin, "departure_date": str(ret_date)})

        payload = {
            "data": {
                "slices": slices,
                "passengers": [{"type": "adult"}],
                "cabin_class": cabin
            }
        }

        try:
            # Step 1: Create an Offer Request
            response = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
            
            if response.status_code == 201:
                data = response.json()
                offers = data['data']['offers']
                if offers:
                    # Show the cheapest offer found
                    best_offer = min(offers, key=lambda x: float(x['total_amount']))
                    st.success(f"Best {cabin.replace('_', ' ')} price found!")
                    st.metric("Total Price", f"{best_offer['total_currency']} {best_offer['total_amount']}")
                    st.info(f"Airline: {best_offer['owner']['name']}")
                else:
                    st.warning("No flights found for those dates/class.")
            else:
                st.error(f"Duffel Error {response.status_code}: {response.text}")
        except Exception as e:
            st.error(f"Search failed: {e}")

with tab2:
    st.header("Search Sports")
    # (Keep your working SeatGeek code here)
    st.write("SeatGeek integration active.")
