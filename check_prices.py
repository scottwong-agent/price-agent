import os
import requests
import pandas as pd
import smtplib
from email.message import EmailMessage
from datetime import datetime
import ast

# --- CONFIGURATION ---
DUFFEL_TOKEN = os.getenv("DUFFEL_TOKEN")
SG_CLIENT_ID = os.getenv("SG_CLIENT_ID")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SHEET_URL = os.getenv("GSHEET_CSV_URL") 

def send_email(item, old_price, new_price, drop_pct, category):
    msg = EmailMessage()
    type_emoji = "✈️" if category == "Flight" else "🏀"
    msg.set_content(f"📉 PRICE DROP ALERT!\n\nTarget: {item}\nOriginal Price: ${old_price}\nCurrent Price: ${new_price}\nTotal Drop: {drop_pct}%")
    msg['Subject'] = f"{type_emoji} {drop_pct}% Price Drop: {item}"
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"✅ Email sent for {item}")
    except Exception as e:
        print(f"❌ Email failed: {e}")

def get_current_flight_price(meta_str):
    try:
        # Convert the string back into a Python dictionary
        m = ast.literal_eval(meta_str)
        headers = {
            "Authorization": f"Bearer {DUFFEL_TOKEN}",
            "Duffel-Version": "v2",
            "Content-Type": "application/json"
        }
        
        # Build slices (Handles One-way OR Round-trip)
        slices = [{"origin": m['origin'], "destination": m['dest'], "departure_date": m['date']}]
        if m.get('type') == "Round-trip" and m.get('return') and m.get('return') != "None":
            slices.append({"origin": m['dest'], "destination": m['origin'], "departure_date": m['return']})

        payload = {
            "data": {
                "slices": slices,
                "passengers": [{"type": "adult"}],
                "cabin_class": m.get('cabin', 'economy') # Uses tracked cabin class
            }
        }
        
        res = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
        if res.status_code == 201:
            offers = res.json()['data']['offers']
            if offers:
                # Return the absolute lowest price for this specific itinerary/cabin
                return float(sorted(offers, key=lambda x: float(x['total_amount']))[0]['total_amount'])
    except Exception as e:
        print(f"Flight API Error: {e}")
    return None

def get_current_sports_price(meta_str):
    try:
        m = ast.literal_eval(meta_str)
        url = f"https://api.seatgeek.com/2/events/{m['event_id']}?client_id={SG_CLIENT_ID}"
        res = requests.get(url).json()
        return res.get('stats', {}).get('lowest_price')
    except Exception as e:
        print(f"Sports API Error: {e}")
    return None

def main():
    if not SHEET_URL:
        print("Error: GSHEET_CSV_URL secret is missing!")
        return

    try:
        df = pd.read_csv(SHEET_URL)
        active_tracks = df[df['Status'].str.strip() == 'Active']
        print(f"--- Checking {len(active_tracks)} items ---")
        
        for _, row in active_tracks.iterrows():
            item = row['Item']
            base_price = float(row['BasePrice'])
            threshold = float(row['Threshold'])
            
            current_price = None
            if row['Category'] == "Flight":
                current_price = get_current_flight_price(row['Metadata'])
            elif row['Category'] == "Sports":
                current_price = get_current_sports_price(row['Metadata'])
            
            if current_price:
                drop_pct = round(((base_price - current_price) / base_price) * 100, 1)
                print(f"Checked {item}: ${current_price} (Target: {threshold}%)")
                
                if drop_pct >= threshold:
                    send_email(item, base_price, current_price, drop_pct, row['Category'])
            else:
                print(f"Skipped {item}: No price data found.")
                
    except Exception as e:
        print(f"General Script Error: {e}")

if __name__ == "__main__":
    main()
