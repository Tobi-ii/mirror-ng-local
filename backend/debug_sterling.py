import sqlite3

conn = sqlite3.connect('mirror.db')
conn.row_factory = sqlite3.Row

print("=" * 70)
print("STERLING BANK FULL DIAGNOSTIC")
print("=" * 70)

# 1. Show ALL Sterling transactions grouped by account_last4
print("\n--- 1. ALL STERLING TRANSACTIONS (grouped by account_last4) ---\n")

last4_groups = conn.execute('''
    SELECT DISTINCT account_last4 FROM transactions WHERE bank = 'Sterling Bank'
''').fetchall()

grand_total_credits = 0
grand_total_debits = 0

for group in last4_groups:
    last4 = group['account_last4'] or 'NULL'
    print(f"\n  Account: •••• {last4}")
    print(f"  {'Date':<22} {'Type':<8} {'Amount':>10}  Narration")
    print(f"  {'-'*70}")
    
    txs = conn.execute('''
        SELECT timestamp, tx_type, amount, narration, balance_after
        FROM transactions 
        WHERE bank = 'Sterling Bank' AND (account_last4 = ? OR (account_last4 IS NULL AND ? = 'NULL'))
        ORDER BY timestamp ASC
    ''', (last4 if last4 != 'NULL' else '', last4)).fetchall()
    
    group_credits = 0
    group_debits = 0
    
    for tx in txs:
        tx_type = tx['tx_type']
        amount = tx['amount']
        if tx_type == 'credit':
            group_credits += amount
        else:
            group_debits += amount
        
        narration = (tx['narration'] or '')[:40]
        print(f"  {tx['timestamp']:<22} {tx_type:<8} {amount:>10,.2f}  {narration}")
    
    print(f"  {'':>22} {'CREDITS:':<8} +{group_credits:>9,.2f}")
    print(f"  {'':>22} {'DEBITS:':<8} -{group_debits:>9,.2f}")
    print(f"  {'':>22} {'NET:':<8}  {group_credits - group_debits:>9,.2f}")
    
    grand_total_credits += group_credits
    grand_total_debits += group_debits

print(f"\n\n--- 2. GRAND TOTALS (ALL Sterling) ---")
print(f"  Total Credits: +{grand_total_credits:,.2f}")
print(f"  Total Debits:  -{grand_total_debits:,.2f}")
print(f"  Grand Net:      {grand_total_credits - grand_total_debits:,.2f}")

# 3. Show what's in account_balances for Sterling
print(f"\n\n--- 3. ACCOUNT_BALANCES TABLE (Sterling only) ---\n")

balances = conn.execute('''
    SELECT id, account_last4, balance, last_updated, is_anchor, adjustment_reason
    FROM account_balances 
    WHERE bank = 'Sterling Bank'
    ORDER BY last_updated DESC
''').fetchall()

if not balances:
    print("  (No entries in account_balances for Sterling)")
else:
    for b in balances:
        anchor_tag = " [ANCHOR]" if b['is_anchor'] else ""
        print(f"  ID: {b['id']:<4} | Last4: ••••{b['account_last4'] or 'NULL':<6} | Balance: {b['balance']:>10,.2f} | Updated: {b['last_updated']} | Reason: {b['adjustment_reason']}{anchor_tag}")

# 4. Simulate what the dashboard shows
print(f"\n\n--- 4. WHAT THE DASHBOARD SHOWS ---\n")

dash_balances = conn.execute('''
    SELECT account_last4, balance, is_anchor
    FROM account_balances
    WHERE bank = 'Sterling Bank'
    ORDER BY last_updated DESC
    LIMIT 1
''').fetchone()

if dash_balances:
    print(f"  Dashboard reads: ₦{dash_balances['balance']:,.2f} (last4: ••••{dash_balances['account_last4'] or 'NULL'})")
else:
    print(f"  Dashboard would fallback to net sum: ₦{grand_total_credits - grand_total_debits:,.2f}")

# 5. Show the math
print(f"\n\n--- 5. EXPECTED MATH ---\n")

anchor = conn.execute('''
    SELECT balance FROM account_balances 
    WHERE bank = 'Sterling Bank' AND is_anchor = 1 LIMIT 1
''').fetchone()

anchor_bal = anchor['balance'] if anchor else 0.0
expected = anchor_bal + grand_total_credits - grand_total_debits

print(f"  Anchor Balance:     {anchor_bal:,.2f}")
print(f"  + Total Credits:   +{grand_total_credits:,.2f}")
print(f"  - Total Debits:    -{grand_total_debits:,.2f}")
print(f"  = Expected Final:   {expected:,.2f}")

if dash_balances:
    actual = dash_balances['balance']
    diff = actual - expected
    if abs(diff) < 0.01:
        print(f"\n  ✅ MATCH! Dashboard shows ₦{actual:,.2f}")
    else:
        print(f"\n  ❌ MISMATCH!")
        print(f"     Dashboard shows:  ₦{actual:,.2f}")
        print(f"     Expected:         ₦{expected:,.2f}")
        print(f"     Difference:       ₦{diff:,.2f}")

conn.close()