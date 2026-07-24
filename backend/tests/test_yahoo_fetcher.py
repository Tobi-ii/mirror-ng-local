from dotenv import load_dotenv
import os
from app.email_fetcher import YahooIMAPFetcher

load_dotenv()

fetcher = YahooIMAPFetcher(
    email_address=os.getenv("YAHOO_EMAIL"),
    app_password=os.getenv("YAHOO_APP_PASSWORD")
)

print("🔍 Connecting to Yahoo IMAP...")
results = fetcher.fetch_alerts(
    sender_patterns=["@sterling.ng", "@alat.ng", "@wema.com"], 
    limit=10
)
print(f"✅ Found {len(results)} bank alerts")
for r in results[:3]:
    print(f"  📩 {r['from']} | {r['subject'][:60]}...")