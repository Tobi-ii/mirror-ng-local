import sqlite3

conn = sqlite3.connect('mirror.db')
conn.row_factory = sqlite3.Row

print("=== Current Account Balances ===\n")
rows = conn.execute('SELECT * FROM account_balances WHERE bank = "Wema Bank" ORDER BY last_updated DESC').fetchall()

for r in rows:
    print(f"Balance: {r['balance']}")
    print(f"Last Updated: {r['last_updated']}")
    print(f"Transaction ID: {r['transaction_id']}")
    print(f"Is Anchor: {r['is_anchor']}")
    print("-" * 60)

print(f"\nTotal Wema balance entries: {len(rows)}")
conn.close()