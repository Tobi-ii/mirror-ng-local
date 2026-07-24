# Contributing a New Bank Parser

Thank you for helping Mirror.ng support more Nigerian banks! This guide will walk you through adding a new bank parser in under 10 minutes.

## How It Works

Mirror.ng reads email alerts from your bank and extracts transaction data. Each bank has a slightly different email format, so we need a custom parser for each bank.

The parser system is designed to be **drop-in** — you just create one file and everything else works automatically.

## Step 1: Find Sample Emails

You need **two sample emails** from the bank you want to add:

1. **A credit alert** (money received)
2. **A debit alert** (money spent)

> ⚠️ **Redact sensitive information** before sharing: account numbers, your name, specific amounts (keep the pattern though!)

Example redacted email:
DEBIT ALERT
Amount: NGN XXX.XX
Account: XXXX1234
Balance: NGN X,XXX.XX
Narration: POS Purchase
Time: DD/MM/YYYY HH:MM:SS


## Step 2: Create the Parser File

Create a new file in `backend/app/parsers/` named `<bank_name>.py` (lowercase, no spaces).

Example: `gtbank.py`, `access.py`, `uba.py`

## Step 3: Copy the Template

Use this template for your new parser:

```python
"""
<bank_name>.py — Parser for <Bank Name> alert emails.

<Bank Name> email format example:
    
    CREDIT ALERT
    Amount: NGN 20,000.00
    Account: XXXX1234
    Balance: NGN 120,450.33
    Narration: Transfer from NAME
    Time: 30/04/2026 09:14:35
"""

from __future__ import annotations
import re
from typing import Optional
from .base import BankParser, Transaction, categorize


class <BankName>Parser(BankParser):
    """
    Parser for <Bank Name> alert emails.
    """
    
    BANK_NAME = "<Bank Name>"
    SENDER_PATTERN = r"<regex pattern that matches the bank's email address>"
    
    def parse(self, subject: str, body: str) -> Optional[Transaction]:
        # TODO: Extract amount
        amount_match = re.search(r"Amount:\s*NGN\s*([\d,]+\.?\d*)", body, re.IGNORECASE)
        if not amount_match:
            return None
        
        amount = self._amount(amount_match.group(1))
        if not amount:
            return None
        
        # TODO: Extract balance
        balance_match = re.search(r"Balance:\s*NGN\s*([\d,]+\.?\d*)", body, re.IGNORECASE)
        balance = self._amount(balance_match.group(1)) if balance_match else None
        
        # TODO: Extract narration
        narration = self._narration(body, "Narration", "Description")
        
        # TODO: Extract timestamp
        time_match = re.search(r"Time:\s*(.+?)(?:\n|$)", body, re.IGNORECASE)
        timestamp = self._date(time_match.group(1)) if time_match else None
        
        # Transaction type (credit/debit)
        tx_type = self._tx_type(subject, body)
        
        # Auto-categorize
        category = categorize(narration) if narration else "other"
        
        return Transaction(
            bank=self.BANK_NAME,
            tx_type=tx_type,
            amount=amount,
            balance=balance,
            narration=narration or subject,
            account_last4=None,  # Extract if available
            timestamp=timestamp,
            category=category,
            raw_email=body[:500]
        )