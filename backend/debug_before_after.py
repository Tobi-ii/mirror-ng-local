import sqlite3

conn = sqlite3.connect('mirror.db')
conn.row_factory = sqlite3.Row

print("=" * 70)
print("BEFORE/AFTER ANCHOR DIAGNOSTIC")
print("=" * 70)

# Show all Sterling transactions grouped by account_last4
print("\n--- CURRENT STATE: All Sterling transactions by account_last4 ---\n")

groups = conn.execute('''
    SELECT account_last4, 
           COUNT(*) as count,
           SUM(CASE WHEN tx_type = 'credit' THEN amount ELSE 0 END) as credits,
           SUM(CASE WHEN tx_type = 'debit' THEN amount ELSE 0 END) as debits
    FROM transactions 
    WHERE bank = 'Sterling Bank'
    GROUP BY account_last4
''').fetchall()

total_credits = 0
total_debits = 0

for g in groups:
    last4 = g['account_last4'] or 'NULL'
    net = g['credits'] - g['debits']
    total_credits += g['credits']
    total_debits += g['debits']
    
    print(f"  Account ••••{last4:<6}: {g['count']:>3} transactions | Credits: +{g['credits']:>10,.2f} | Debits: -{g['debits']:>10,.2f} | Net: {net:>10,.2f}")

print(f"\n  GRAND TOTAL: Credits: +{total_credits:>10,.2f} | Debits: -{total_debits:>10,.2f} | Net: {total_credits - total_debits:>10,.2f}")

# Show what's in account_balances
print("\n--- CURRENT STATE: account_balances for Sterling ---\n")

balances = conn.execute('''
    SELECT account_last4, balance, is_anchor, adjustment_reason
    FROM account_balances 
    WHERE bank = 'Sterling Bank'
    ORDER BY last_updated DESC
''').fetchall()

if not balances:
    print("  (No entries - anchor not yet set)")
else:
    for b in balances:
        anchor_tag = " [ANCHOR]" if b['is_anchor'] else ""
        print(f"  Account ••••{b['account_last4'] or 'NULL':<6}: Balance: {b['balance']:>10,.2f} | Reason: {b['adjustment_reason']}{anchor_tag}")

# Check for any transactions with weird account_last4 values
print("\n--- CHECKING FOR WEIRD account_last4 VALUES ---\n")

weird = conn.execute('''
    SELECT DISTINCT account_last4, COUNT(*) as count
    FROM transactions
    WHERE bank = 'Sterling Bank'
    AND (account_last4 IS NULL OR account_last4 = '' OR account_last4 = '0000' OR account_last4 = '000' OR account_last4 = '00' OR account_last4 = '0')
    GROUP BY account_last4
''').fetchall()

if weird:
    print("  Found transactions with placeholder account_last4:")
    for w in weird:
        val = w['account_last4'] if w['account_last4'] else 'NULL'
        print(f"    '{val}': {w['count']} transactions")
else:
    print("  ✓ No placeholder account_last4 values found")

conn.close()