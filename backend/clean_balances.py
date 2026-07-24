import sqlite3

conn = sqlite3.connect('mirror.db')
conn.row_factory = sqlite3.Row

print("=== Cleaning Account Balances ===\n")

# 1. Find the absolute latest balance for each bank/account from the transactions table
latest_balances = conn.execute('''
    SELECT bank, account_last4, balance_after 
    FROM transactions 
    WHERE (bank, account_last4, timestamp) IN (
        SELECT bank, account_last4, MAX(timestamp) 
        FROM transactions 
        GROUP BY bank, account_last4
    )
''').fetchall()

print(f"Found {len(latest_balances)} unique accounts to fix.")

# 2. Wipe the messy account_balances table completely
conn.execute('DELETE FROM account_balances')
print("Cleared old account_balances table.")

# 3. Insert exactly ONE correct row per account
user_id = conn.execute('SELECT user_id FROM transactions LIMIT 1').fetchone()['user_id']

for row in latest_balances:
    # ✅ FIX: Added last_updated column with current timestamp
    conn.execute('''
        INSERT INTO account_balances (user_id, bank, account_last4, balance, last_updated)
        VALUES (?, ?, ?, ?, datetime('now'))
    ''', (user_id, row['bank'], row['account_last4'], row['balance_after']))
    print(f"✅ Fixed {row['bank']} (••••{row['account_last4']}): {row['balance_after']}")

conn.commit()
conn.close()
print("\nDone! Dashboard balances are now fixed.")