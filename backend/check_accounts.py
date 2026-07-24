import sqlite3

conn = sqlite3.connect('mirror.db')
conn.row_factory = sqlite3.Row

print("=== Account Balances Table ===\n")
rows = conn.execute('SELECT * FROM account_balances').fetchall()

for r in rows:
    print(f"Bank: {r['bank']}")
    print(f"Last4: {r['account_last4']}")
    print(f"Stored Balance: {r['balance']}")
    print("-" * 40)

conn.close()