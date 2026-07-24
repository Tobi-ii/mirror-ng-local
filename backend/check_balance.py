import sqlite3

conn = sqlite3.connect('mirror.db')
conn.row_factory = sqlite3.Row

print("=== Last 10 Wema Transactions ===\n")
rows = conn.execute('''
    SELECT timestamp, narration, amount, balance_after 
    FROM transactions 
    WHERE bank = 'Wema Bank' 
    ORDER BY timestamp DESC 
    LIMIT 10
''').fetchall()

for r in rows:
    print(f"Date: {r['timestamp']}")
    print(f"Amount: {r['amount']}")
    print(f"Balance After: {r['balance_after']}")
    print(f"Narration: {r['narration'][:60]}")
    print("-" * 80)

conn.close()