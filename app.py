import streamlit as st
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="Price Agent", layout="wide")
st.title("🤖 Elite Price Agent")

# --- 1. DEFINE TABS FIRST ---
tab1, tab2 = st.tabs(["✈️ Flights", "🏀 Sports"])

# --- 2. FLIGHTS SECTION ---
with tab1:
    st.header("Search Flights")
    
    col_settings, col_dates = st.columns([1, 2])
    with col_settings:
        trip_type = st.radio("Trip Type", ["One-Way", "Round-Trip"], horizontal=True)
        cabin = st.selectbox("Cabin Class", ["economy", "premium_economy", "business", "first"])
    
    with col_dates:
        col_origin, col_dest = st.columns(2)
        origin = col_origin.text_input("From (IATA Code)", "JFK").upper().strip()
        dest = col_dest.text_input("To (IATA Code)", "LAX").upper().strip()
        
        col_d1, col_d2 = st.columns(2)
        dep_date = col_d1.date_input("Departure", datetime.now() + timedelta(days=14))
        ret_date = col_d2.date_input("Return", datetime.now() + timedelta(days=21))

    if st.button("🔍 Find Top 3 Lowest Prices"):
        # Safety check for Secrets
        if "DUFFEL_TOKEN" not in st.secrets:
            st.error("Missing DUFFEL_TOKEN in Secrets!")
            st.stop()

        headers = {
            "Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}",
            "Duffel-Version": "v2",
            "Content-Type": "application/json"
        }

        slices = [{"origin": origin, "destination": dest, "departure_date": str(dep_date)}]
        if trip_type == "Round-Trip":
            slices.append({"origin": dest, "destination": origin, "departure_date": str(ret_date)})

        payload = {"data": {"slices": slices, "passengers": [{"type": "adult"}], "cabin_class": cabin}}

        with st.spinner("Analyzing airline data..."):
            response = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
            
            if response.status_code == 201:
                offers = response.json()['data']['offers']
                if offers:
                    # Sort by price
                    sorted_offers = sorted(offers, key=lambda x: float(x['total_amount']))
                    top_3 = sorted_offers[:3]
                    
                    st.divider()
                    st.subheader(f"🏆 Top 3 {cabin.title()} Options")
                    
                    for idx, offer in enumerate(top_3):
                        with st.container():
                            c1, c2 = st.columns([1, 3])
                            c1.metric(f"Option {idx+1}", f"{offer['total_currency']} {offer['total_amount']}")
                            
                            with c2:
                                for i, s in enumerate(offer['slices']):
                                    leg = "🛫 Outbound" if i == 0 else "🛬 Return"
                                    seg = s['segments'][0]
                                    airline = seg['marketing_carrier']['name']
                                    f_no = f"{seg['marketing_carrier']['iata_code']}{seg['marketing_carrier_flight_number']}"
                                    d_time = seg['departing_at'].replace('T', ' ')[:16]
                                    st.write(f"**{leg}:** {airline} ({f_no}) at {d_time}")
                            st.divider()
                else:
                    st.warning("No flights found for these criteria.")
            else:
                st.error(f"Duffel Error: {response.json()['errors'][0]['message']}")

# --- 3. SPORTS SECTION ---
with tab2:
    st.header("🏀 Sports Price Tracker")
    team = st.text_input("Enter Team (e.g., Lakers, Yankees)", "Lakers")
    
    if st.button("Check Ticket Prices"):
        if "SG_CLIENT_ID" not in st.secrets:
            st.error("Missing SG_CLIENT_ID in Secrets!")
        else:
            client_id = st.secrets["SG_CLIENT_ID"]
            url = f"https://api.seatgeek.com/2/events?q={team}&client_id={client_id}"
            try:
                data = requests.get(url).json()
                if data.get('events'):
                    event = data['events'][0]
                    price = event['stats'].get('lowest_price')
                    if price:
                        st.metric(label=event['title'], value=f"${price}")
                        st.write(f"📍 Venue: {event['venue']['name']}")
                    else:
                        st.info("Event found, but no pricing data is available yet.")
                else:
                    st.warning("No upcoming events found for that team.")
            except Exception as e:
                st.error(f"SeatGeek Error: {e}")
