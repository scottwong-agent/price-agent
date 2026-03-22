import streamlit as st
import requests
from datetime import datetime, timedelta

# --- TRIP SETTINGS (Now inside the tab) ---
with tab1:
    st.header("✈️ Search Flights")
    
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

    if st.button("🔍 Find Top 3 Lowest Prices"):
        headers = {
            "Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}",
            "Duffel-Version": "v2",
            "Content-Type": "application/json"
        }

        slices = [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}]
        if trip_type == "Round-Trip":
            slices.append({"origin": dest, "destination": origin, "departure_date": str(ret_date)})

        payload = {"data": {"slices": slices, "passengers": [{"type": "adult"}], "cabin_class": cabin}}

        with st.spinner("Finding the cheapest seats..."):
            response = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
            
            if response.status_code == 201:
                offers = response.json()['data']['offers']
                if offers:
                    # SORTING: Sort all offers by total_amount (price)
                    sorted_offers = sorted(offers, key=lambda x: float(x['total_amount']))
                    
                    # TAKE TOP 3: slice the first three items
                    top_3 = sorted_offers[:3]
                    
                    st.divider()
                    st.subheader(f"🏆 Top 3 Lowest {cabin.title()} Prices")
                    
                    for idx, offer in enumerate(top_3):
                        # Create a "card" for each offer
                        with st.container():
                            col_price, col_details = st.columns([1, 3])
                            
                            # Price Column
                            col_price.metric(f"Option #{idx+1}", f"{offer['total_currency']} {offer['total_amount']}")
                            
                            # Details Column
                            with col_details:
                                for i, s in enumerate(offer['slices']):
                                    label = "🛫 Departure" if i == 0 else "🛬 Return"
                                    # Get info from the first segment of the slice
                                    seg = s['segments'][0]
                                    airline = seg['marketing_carrier']['name']
                                    f_no = f"{seg['marketing_carrier']['iata_code']} {seg['marketing_carrier_flight_number']}"
                                    d_time = seg['departing_at'].replace('T', ' ')[:16]
                                    
                                    st.write(f"**{label}:** {airline} ({f_no}) at {d_time}")
                            st.divider()
                else:
                    st.warning("No flights found. Try expanding your search criteria.")
            else:
                st.error(f"Error: {response.json()['errors'][0]['message']}")
