from app.database import get_db
from app.balance_manager import BalanceManager

conn = get_db()
bm = BalanceManager(conn)

# Manually set the anchor balance for Sterling Bank
bm.set_initial_balance(
    user_id='1', 
    bank='Sterling Bank', 
    account_last4='5156', 
    balance=5.0
)

conn.commit()
conn.close()
print("✅ Sterling anchor balance set to 5.0")