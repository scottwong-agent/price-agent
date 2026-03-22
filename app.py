import streamlit as st
import requests
from amadeus import Client

st.set_page_config(page_title="Price Agent", layout="centered")

st.title("✈️ Price Tracker Agent")

# Checking if secrets are set up
if "AMADEUS_KEY" not in st.secrets:
    st.error("Missing API Keys! Please add them to the 'Secrets' section in Streamlit settings.")
    st.stop()

# Initialize Amadeus
amadeus = Client(
    client_id=st.secrets["AMADEUS_KEY"],
    client_secret=st.secrets["AMADEUS_SECRET"]
)

# --- FLIGHT SECTION ---
st.header("Search Flights")
col1, col2 = st.columns(2)
origin = col1.text_input("From (Airport Code)", "LHR")
dest = col2.text_input("To (Airport Code)", "JFK")
date = st.date_input("Date")
cabin = st.selectbox("Class", ["ECONOMY", "BUSINESS", "FIRST"])

if st.button("Find Best Price"):
    try:
        res = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=dest,
            departureDate=str(date),
            adults=1,
            travelClass=cabin
        )
        if res.data:
            price = res.data[0]['price']['total']
            st.success(f"The best {cabin} price is ${price}")
        else:
            st.info("No flights found for that date.")
    except Exception as e:
        st.error(f"Flight API Error: {e}")

st.divider()
st.caption("Agent is running live. Share this URL with friends!")
