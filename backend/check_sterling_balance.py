import sqlite3

conn = sqlite3.connect('mirror.db')
conn.row_factory = sqlite3.Row

print("=== Sterling Bank Balance Verification ===\n")

# Get all Sterling accounts (grouped by last4)
accounts = conn.execute('''
    SELECT DISTINCT account_last4 FROM transactions WHERE bank = 'Sterling Bank'
''').fetchall()

if not accounts:
    print("No Sterling Bank transactions found in database.")
else:
    for acc in accounts:
        last4 = acc['account_last4'] or 'Unknown'
        print(f"--- Account ending in •••• {last4} ---")

        # 1. Get Initial/Anchor Balance (What user entered in onboarding)
        anchor = conn.execute('''
            SELECT balance FROM account_balances
            WHERE bank = 'Sterling Bank' AND account_last4 = ? AND is_anchor = 1
            LIMIT 1
        ''', (last4,)).fetchone()

        initial_balance = anchor['balance'] if anchor else 0.0
        print(f"1. Initial Balance (Anchor): {initial_balance:,.2f}")

        # 2. Get Total Credits
        credits = conn.execute('''
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions 
            WHERE bank = 'Sterling Bank' AND account_last4 = ? AND tx_type = 'credit'
        ''', (last4,)).fetchone()
        total_credits = credits['total']
        print(f"2. Total Credits:            +{total_credits:,.2f}")

        # 3. Get Total Debits
        debits = conn.execute('''
            SELECT COALESCE(SUM(amount), 0) as total
            FROM transactions 
            WHERE bank = 'Sterling Bank' AND account_last4 = ? AND tx_type = 'debit'
        ''', (last4,)).fetchone()
        total_debits = debits['total']
        print(f"3. Total Debits:             -{total_debits:,.2f}")

        # 4. Calculate Expected Balance
        expected_balance = initial_balance + total_credits - total_debits
        print(f"-----------------------------------------")
        print(f"4. EXPECTED FINAL BALANCE:   ₦{expected_balance:,.2f}")

        # 5. Check what the DB currently shows on the dashboard
        current = conn.execute('''
            SELECT balance FROM account_balances
            WHERE bank = 'Sterling Bank' AND account_last4 = ? AND is_anchor = 0
            ORDER BY last_updated DESC LIMIT 1
        ''', (last4,)).fetchone()

        current_balance = current['balance'] if current else 0.0
        print(f"5. CURRENT DB BALANCE:       ₦{current_balance:,.2f}")

        if abs(expected_balance - current_balance) < 0.01:
            print("✅ MATCH! The calculation is correct.")
        else:
            print(f"❌ MISMATCH! Difference: ₦{expected_balance - current_balance:,.2f}")
        print()

conn.close()