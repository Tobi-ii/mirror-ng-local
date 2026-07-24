import sqlite3

conn = sqlite3.connect('mirror.db')
conn.row_factory = sqlite3.Row

print("=== All Banks Balance Check ===\n")

banks = conn.execute('SELECT DISTINCT bank FROM transactions').fetchall()

for bank_row in banks:
    bank = bank_row['bank']
    print(f"--- {bank} ---")
    
    credits = conn.execute('''
        SELECT COALESCE(SUM(amount), 0) as total
        FROM transactions WHERE bank = ? AND tx_type = 'credit'
    ''', (bank,)).fetchone()['total']
    
    debits = conn.execute('''
        SELECT COALESCE(SUM(amount), 0) as total
        FROM transactions WHERE bank = ? AND tx_type = 'debit'
    ''', (bank,)).fetchone()['total']
    
    print(f"Credits: +{credits:,.2f}")
    print(f"Debits:  -{debits:,.2f}")
    print(f"Net:     {credits - debits:,.2f}\n")

conn.close()