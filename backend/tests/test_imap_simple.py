# backend/test_imap_simple.py
#!/usr/bin/env python3
"""Simple test script for Yahoo IMAP + parser integration"""
from dotenv import load_dotenv
import os
import sys

# Add parent directory to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.email_fetcher import YahooIMAPFetcher
from app.parsers.base import BankParser

def main():
    load_dotenv()
    
    yahoo_email = os.getenv("YAHOO_EMAIL")
    yahoo_app_password = os.getenv("YAHOO_APP_PASSWORD")
    
    if not yahoo_email or not yahoo_app_password:
        print("❌ ERROR: YAHOO_EMAIL or YAHOO_APP_PASSWORD not set in .env")
        print("   Please edit backend/.env and add your Yahoo credentials")
        return
    
    print(f"🔍 Connecting to Yahoo IMAP as {yahoo_email}...")
    
    try:
        fetcher = YahooIMAPFetcher(yahoo_email, yahoo_app_password)
        alerts = fetcher.fetch_alerts(
            sender_patterns=["@sterling.ng", "@alat.ng", "@wema.com"], 
            limit=5
        )
        
        print(f"✅ Found {len(alerts)} bank alert emails\n")
        
        if not alerts:
            print("💡 Tip: Make sure your Yahoo account receives alerts from these banks")
            print("   and that IMAP access is enabled in Yahoo settings.")
            return
        
        for i, alert in enumerate(alerts, 1):
            print(f"--- Email {i} ---")
            print(f"From: {alert['from']}")
            print(f"Subject: {alert['subject'][:70]}...")
            
            tx = BankParser.parse_from_raw(alert["raw"], alert["from"])
            if tx:
                print(f"✅ Parsed: {tx.bank} | {tx.tx_type} | ₦{tx.amount:,.2f}")
                if tx.balance:
                    print(f"   Balance in email: ₦{tx.balance:,.2f}")
                print(f"   Narration: {tx.narration[:60]}...")
            else:
                print(f"⚠️  Could not parse (may need parser update)")
            print()
            
    except ValueError as e:
        print(f"❌ Auth error: {e}")
        print("💡 Check your Yahoo App Password at https://login.yahoo.com/account/security")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()