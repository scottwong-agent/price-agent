name: Daily Price Intelligence Check
on:
  schedule:
    - cron: '0 13 * * *' 
  workflow_dispatch: 

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install pandas requests
      - name: Run Price Checker
        env:
          DUFFEL_TOKEN: ${{ secrets.DUFFEL_TOKEN }}
          SG_CLIENT_ID: ${{ secrets.SG_CLIENT_ID }}
          EMAIL_SENDER: ${{ secrets.EMAIL_SENDER }}
          EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
          EMAIL_RECEIVER: ${{ secrets.EMAIL_RECEIVER }}
          GSHEET_CSV_URL: ${{ secrets.GSHEET_CSV_URL }}
        run: python check_prices.py
