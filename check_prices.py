import os, requests, pandas as pd, smtplib, ast
from email.message import EmailMessage
from datetime import datetime

DUFFEL_TOKEN = os.getenv("DUFFEL_TOKEN")
SG_CLIENT_ID = os.getenv("SG_CLIENT_ID")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SHEET_URL = os.getenv("GSHEET_CSV_URL") 

def send_email(item, old_p, new_p, drop, cat):
    msg = EmailMessage()
    msg.set_content(f"📉 PRICE DROP!\n\nRoute: {item}\nWas: ${old_p}\nNow: ${new_p}\nDrop: {drop}%")
    msg['Subject'] = f"🚨 {drop}% Drop: {item}"
    msg['From'], msg['To'] = EMAIL_SENDER, EMAIL_RECEIVER
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
    except Exception as e: print(f"Email error: {e}")

def get_flight_price(meta_str):
    try:
        m = ast.literal_eval(meta_str)
        slices = [{"origin": m['origin'], "destination": m['dest'], "departure_date": m['date']}]
        if m.get('type') == "Round-trip" and m.get('return') != "None":
            slices.append({"origin": m['dest'], "destination": m['origin'], "departure_date": m['return']})
        
        res = requests.post("https://api.duffel.com/air/offer_requests", 
                            json={"data": {"slices": slices, "passengers": [{"type": "adult"}], "cabin_class": m.get('cabin', 'economy')}},
                            headers={"Authorization": f"Bearer {DUFFEL_TOKEN}", "Duffel-Version": "v2", "Content-Type": "application/json"})
        if res.status_code == 201:
            prices = [float(o['total_amount']) for o in res.json()['data']['offers']]
            return min(prices) if prices else None
    except: return None

def main():
    if not SHEET_URL: return
    try:
        df = pd.read_csv(SHEET_URL)
        for _, row in df[df['Status'] == 'Active'].iterrows():
            current = get_flight_price(row['Metadata']) if row['Category'] == "Flight" else None
            if current:
                drop = round(((float(row['BasePrice']) - current) / float(row['BasePrice'])) * 100, 1)
                if drop >= float(row['Threshold']):
                    send_email(row['Item'], row['BasePrice'], current, drop, row['Category'])
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    main()
