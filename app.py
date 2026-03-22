import streamlit as st
import requests

st.set_page_config(page_title="Price Agent", page_icon="🤖")

st.title("🤖 My Personal Price Agent")

# --- SECRET VALIDATION ---
if "SG_CLIENT_ID" not in st.secrets or "DUFFEL_TOKEN" not in st.secrets:
    st.error("Missing API Keys! Please add 'SG_CLIENT_ID' and 'DUFFEL_TOKEN' to the Secrets section.")
    st.stop()

tab1, tab2 = st.tabs(["🏀 Sports (SeatGeek)", "✈️ Flights (Duffel)"])

with tab1:
    st.header("Search Sports")
    team = st.text_input("Enter Team Name", "Lakers")
    if st.button("Find Lowest Ticket"):
        client_id = st.secrets["SG_CLIENT_ID"]
        url = f"https://api.seatgeek.com/2/events?q={team}&client_id={client_id}"
        try:
            data = requests.get(url).json()
            if data['events']:
                event = data['events'][0]
                price = event['stats']['lowest_price']
                st.metric(label=event['title'], value=f"${price}")
                st.write(f"📍 {event['venue']['name']}")
            else:
                st.warning("No events found.")
        except Exception as e:
            st.error(f"Error connecting to SeatGeek: {e}")

with tab2:
    st.header("Search Flights")
    st.info("Duffel Flight Integration Active")
    origin = st.text_input("From (Airport Code)", "JFK")
    dest = st.text_input("To (Airport Code)", "LAX")
    
    if st.button("Check Duffel Prices"):
        # This is a simplified check to verify your token works
        headers = {
            "Authorization": f"Bearer {st.secrets['DUFFEL_TOKEN']}",
            "Duffel-Version": "beta",
            "Content-Type": "application/json"
        }
        res = requests.get("https://api.duffel.com/air/airports", headers=headers)
        if res.status_code == 200:
            st.success("✅ Duffel Connection Successful! Ready to search.")
        else:
            st.error(f"Duffel Error: {res.status_code}. Check your token.")

st.sidebar.markdown("---")
st.sidebar.write("Agent status: **Online**")
