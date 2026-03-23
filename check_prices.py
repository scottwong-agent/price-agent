import os
import requests
import pandas as pd
import smtplib
from email.message import EmailMessage
from datetime import datetime
import ast

# --- CONFIGURATION (Pulling from GitHub Secrets) ---
DUFFEL_TOKEN = os.getenv("DUFFEL_TOKEN")
SG_CLIENT_ID = os.getenv("SG_CLIENT_ID")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SHEET_URL = os.getenv("GSHEET_CSV_URL") 

def send_email(item, old_price, new_price, drop_pct):
    msg = EmailMessage()
    msg.set_content(f"📉 PRICE DROP ALERT!\n\nTarget: {item}\nOriginal Price: ${old_price}\nCurrent Price: ${new_price}\nTotal Drop: {drop_pct}%")
    msg['Subject'] = f"🚨 {drop_pct}% Price Drop: {item}"
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
        m = ast.literal_eval(meta_str)
        headers = {
            "Authorization": f"Bearer {DUFFEL_TOKEN}",
            "Duffel-Version": "v2",
            "Content-Type": "application/json"
        }
        payload = {
            "data": {
                "slices": [{"origin": m['origin'], "destination": m['dest'], "departure_date": m['date']}],
                "passengers": [{"type": "adult"}],
                "cabin_class": "economy"
            }
        }
        res = requests.post("https://api.duffel.com/air/offer_requests", json=payload, headers=headers)
        if res.status_code == 201:
            offers = res.json()['data']['offers']
            if offers:
                return float(sorted(offers, key=lambda x: float(x['total_amount']))[0]['total_amount'])
    except Exception as e:
        print(f"Flight API Error: {e}")
    return None

def get_current_sports_price(meta_str):
    try:
        m = ast.literal_eval(meta_str)
        url = f"https://api.seatgeek.com/2/events/{m['event_id']}?client_id={SG_CLIENT_ID}"
        res = requests.get(url).json()
        stats = res.get('stats', {})
        return stats.get('lowest_price') or stats.get('average_price')
    except Exception as e:
        print(f"Sports API Error: {e}")
    return None

def main():
    print(f"--- Starting Price Check: {datetime.now()} ---")
    if not SHEET_URL:
        print("Error: GSHEET_CSV_URL secret is missing!")
        return

    try:
        # Load the Tracking sheet from Google
        df = pd.read_csv(SHEET_URL)
        
        # We only care about rows where Status is 'Active'
        active_tracks = df[df['Status'].str.strip() == 'Active']
        print(f"Found {len(active_tracks)} active tracks.")
        
        for idx, row in active_tracks.iterrows():
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
                print(f"Checking {item}: Current ${current_price} (Target drop: {threshold}%)")
                
                if drop_pct >= threshold:
                    send_email(item, base_price, current_price, drop_pct)
                else:
                    print(f"No alert needed. Drop is only {drop_pct}%")
            else:
                print(f"Could not get live price for {item}")
                
    except Exception as e:
        print(f"General Script Error: {e}")

if __name__ == "__main__":
    main()
