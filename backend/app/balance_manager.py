import sqlite3
import logging
from typing import Optional, List, Dict
from datetime import datetime
from .database import get_db

logger = logging.getLogger(__name__)

class BalanceManager:
    """Manages running balances starting from user-provided initial balance"""
    
    def __init__(self, db_connection=None):
        self.db = db_connection or get_db()

    def _last4(self, account_last4: str) -> str:
        if not account_last4:
            return ""
        return str(account_last4)[-4:]
    
    def set_initial_balance(
        self, 
        user_id: str, 
        bank: str, 
        account_last4: str, 
        balance: float,
        as_of: Optional[datetime] = None
    ):
        standard_last4 = self._last4(account_last4)
        
        cursor = self.db.execute('''
            SELECT MIN(timestamp) as first_tx
            FROM transactions
            WHERE user_id = ? AND bank = ? AND account_last4 = ?
        ''', (user_id, bank, standard_last4))
        row = cursor.fetchone()
        
        if row and row['first_tx']:
            first_tx = row['first_tx']
        elif as_of:
            first_tx = as_of.isoformat()
        else:
            first_tx = datetime.now().isoformat()
        
        # Delete all existing balance entries for this bank/account
        self.db.execute('''
            DELETE FROM account_balances
            WHERE user_id = ? AND bank = ? AND account_last4 = ?
        ''', (user_id, bank, standard_last4))
        
        # Insert the anchor balance
        self.db.execute('''
            INSERT INTO account_balances 
            (user_id, bank, account_last4, balance, last_updated, transaction_id, adjustment_reason, is_anchor)
            VALUES (?, ?, ?, ?, ?, NULL, 'initial_balance', 1)
        ''', (user_id, bank, standard_last4, balance, first_tx))
        
        cursor = self.db.execute('''
            SELECT id, tx_type, amount, timestamp
            FROM transactions
            WHERE user_id = ? AND bank = ? AND account_last4 = ?
            ORDER BY timestamp ASC
        ''', (user_id, bank, standard_last4))
        
        transactions = cursor.fetchall()
        if transactions:
            current_balance = balance
            for tx_row in transactions:
                tx_id = tx_row['id']
                tx_type = tx_row['tx_type']
                amount = tx_row['amount']
                
                if tx_type == 'credit':
                    current_balance += amount
                else:
                    current_balance -= amount
                
                # ✅ FIX: ONLY update the transaction's balance_after column for history.
                # Do NOT insert a new row into account_balances for every transaction.
                self.db.execute('''
                    UPDATE transactions SET balance_after = ? WHERE id = ?
                ''', (current_balance, tx_id))
            
            # ✅ FIX: After the loop, insert ONLY the final current balance
            self.db.execute('''
                INSERT INTO account_balances
                (user_id, bank, account_last4, balance, last_updated, transaction_id, adjustment_reason, is_anchor)
                VALUES (?, ?, ?, ?, datetime('now'), NULL, 'recalculated', 0)
            ''', (user_id, bank, standard_last4, current_balance))
        
        self.db.commit()
    
    def update_balance_from_transaction(
        self, 
        user_id: str, 
        transaction
    ) -> Optional[float]:
        tx_last4 = self._last4(transaction.account_last4)
        
        # If the email itself contains a balance (like Wema/OPay), use it directly
        if transaction.balance is not None:
            self._store_balance(user_id, transaction, transaction.balance)
            return transaction.balance
        
        # Read the LATEST balance (Anchor OR last running balance).
        # This allows accumulation to chain correctly on subsequent syncs.
        latest = self.db.execute('''
            SELECT balance FROM account_balances
            WHERE user_id = ? AND bank = ? AND account_last4 = ?
            ORDER BY last_updated DESC LIMIT 1
        ''', (user_id, transaction.bank, tx_last4)).fetchone()

        if not latest:
            return None 
        
        current = latest['balance']
        
        if transaction.tx_type == 'credit':
            new_balance = current + transaction.amount
        else:
            new_balance = current - transaction.amount
        
        self._store_balance(user_id, transaction, new_balance)
        return new_balance
    
    def _store_balance(self, user_id, transaction, balance: float):
        standard_last4 = self._last4(transaction.account_last4)
        
        # ✅ FIX: Delete any existing non-anchor balance entries
        self.db.execute('''
            DELETE FROM account_balances 
            WHERE user_id = ? AND bank = ? AND account_last4 = ? AND is_anchor = 0
        ''', (user_id, transaction.bank, standard_last4))
        
        self.db.execute('''
        INSERT INTO account_balances 
        (user_id, bank, account_last4, balance, last_updated, transaction_id, adjustment_reason, is_anchor)
        VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
        ''', (
            user_id,
            transaction.bank,
            standard_last4,
            balance,
            datetime.now().isoformat(),
            getattr(transaction, 'id', None),
            0
        ))
        self.db.commit()

    def manual_adjust(
        self, 
        user_id: str, 
        bank: str, 
        account_last4: str, 
        new_balance: float,
        reason: str = "manual_adjustment"
    ):
        standard_last4 = self._last4(account_last4)
        
        # ✅ FIX: Delete existing non-anchor balances first
        self.db.execute('''
            DELETE FROM account_balances 
            WHERE user_id = ? AND bank = ? AND account_last4 = ? AND is_anchor = 0
        ''', (user_id, bank, standard_last4))
        
        self.db.execute('''
            INSERT INTO account_balances 
            (user_id, bank, account_last4, balance, last_updated, transaction_id, adjustment_reason, is_anchor)
            VALUES (?, ?, ?, ?, ?, NULL, ?, 1)
        ''', (
            user_id, 
            bank, 
            standard_last4, 
            new_balance, 
            datetime.now().isoformat(),
            reason
        ))
        self.db.commit()
    
    def get_current_balance(
        self, 
        user_id: str, 
        bank: str, 
        account_last4: str
    ) -> Optional[float]:
        standard_last4 = self._last4(account_last4)
        cursor = self.db.execute('''
            SELECT balance FROM account_balances 
            WHERE user_id = ? AND bank = ? AND account_last4 = ?
            ORDER BY last_updated DESC
            LIMIT 1
        ''', (user_id, bank, standard_last4))
        row = cursor.fetchone()
        if row:
            return row['balance']
        return self._compute_net_balance(user_id, bank, standard_last4)
    
    def _compute_net_balance(self, user_id: str, bank: str, account_last4: str) -> Optional[float]:
        cursor = self.db.execute('''
            SELECT SUM(CASE WHEN tx_type = 'credit' THEN amount ELSE -amount END)
            FROM transactions
            WHERE user_id = ? AND bank = ? AND account_last4 = ?
        ''', (user_id, bank, account_last4))
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None
    
    def get_all_current_balances(self, user_id: str) -> List[Dict]:
        cursor = self.db.execute('''
            SELECT DISTINCT bank, account_last4 FROM transactions WHERE user_id = ?
            UNION
            SELECT DISTINCT bank, account_last4 FROM account_balances WHERE user_id = ?
        ''', (user_id, user_id))
        accounts = cursor.fetchall()
        
        result = []
        for row in accounts:
            bank = row['bank']
            last4 = row['account_last4'] or ''
            standard_last4 = self._last4(last4)
            
            cur = self.db.execute('''
                SELECT balance, last_updated, is_anchor
                FROM account_balances
                WHERE user_id = ? AND bank = ? AND account_last4 = ?
                ORDER BY last_updated DESC
                LIMIT 1
            ''', (user_id, bank, standard_last4))
            bal_row = cur.fetchone()
            
            if bal_row:
                balance = bal_row['balance']
                last_updated = bal_row['last_updated']
                is_anchor = bal_row['is_anchor']
            else:
                net = self._compute_net_balance(user_id, bank, standard_last4)
                balance = net if net is not None else 0.0
                last_updated = None
                is_anchor = 0
            
            result.append({
                'bank': bank,
                'account_last4': standard_last4,
                'balance': balance,
                'last_updated': last_updated,
                'is_anchor': is_anchor,
                'provides_balance': False,
            })
        
        return result