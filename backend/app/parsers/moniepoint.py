"""
moniepoint.py — Moniepoint Bank alert email parser

Handles: Moniepoint credit/debit email alerts from no-reply@moniepoint.com

Supported formats:
  - Credit alert: subject "Credit alert!", credit amount, balance with N prefix
  - Debit alert:  subject "Debit alert!", debit amount, transaction details
  - Both formats include: full account number (last 4 used), sender name,
    narration, date in "22 May, 2026 | 10:28:56 AM" format

Sender:  no-reply@moniepoint.com

──────────────────────────────────────────────────────────
Sample CREDIT alert (Moniepoint)
──────────────────────────────────────────────────────────
Subject: Credit alert!

Hi [CUSTOMER NAME],

We wish to inform you that a credit transaction occurred
on your account with us.

Credit Amount
 9,500.00

Transaction Details

Account Balance:
N 10,256.12

Account Number:
[FULL ACCOUNT NUMBER]

Sender's Name:
from [SENDER NAME]

Date & Time:
22 May, 2026 | 10:28:56 AM

Narration:
MOBILE TRF TO MMF [NARRATION]
──────────────────────────────────────────────────────────
Note: Moniepoint exposes full account number in email.
Amount has no currency prefix — just a plain number.
Balance uses "N" prefix (not NGN or ₦).
Date format: "22 May, 2026 | 10:28:56 AM"
──────────────────────────────────────────────────────────
"""

import re
import logging
from datetime import datetime
from typing import Optional
from .base import BankParser, ParsedTransaction, categorize

logger = logging.getLogger(__name__)


class MoniepointParser(BankParser):
    """Parses Moniepoint debit/credit email alerts.

    Matches sender as no-reply@moniepoint.com or any address containing "moniepoint".
    Provides parsed balance, amount, account suffix, narration, and timestamp.

    Narration formats parsed:
      - "MOBILE TRF TO MMF [description]" — mobile money transfer
      - "POS PURCHASE [merchant]" — point-of-sale debit
      - "TRANSFER FROM [sender]" — incoming transfer
      - "WITHDRAWAL [ATM location]" — ATM withdrawal
    """

    BANK_NAME        = "Moniepoint"
    # Matches either the official sender address or any moniepoint subdomain
    SENDER_PATTERN   = r"no-reply@moniepoint\.com|moniepoint"
    PROVIDES_BALANCE = True

    def parse(self, subject: str, body: str) -> Optional[ParsedTransaction]:
        """Extract transaction details from a Moniepoint alert email.

        Args:
            subject: Email subject line (e.g. "Credit alert!" or "Debit alert!")
            body:    Plain-text email body with transaction details

        Returns:
            ParsedTransaction with bank, type, amount, balance, narration, etc.,
            or None if no amount pattern is found (not a valid Moniepoint alert).

        Examples of narration strings parsed:
            "MOBILE TRF TO MMF John Doe"
            "TRANSFER FROM Jane Smith"
            "POS PURCHASE ShopRite"
            "WITHDRAWAL ATM Main St"
        """

        # --- Transaction type: determined from subject line keywords ---
        if re.search(r"credit", subject, re.IGNORECASE):
            tx_type = "credit"
        elif re.search(r"debit", subject, re.IGNORECASE):
            tx_type = "debit"
        else:
            # Fallback: parse type from body content (e.g. "Credit Amount" / "Debit Amount")
            tx_type = self._tx_type(subject, body)

        # --- Amount: captures the numeric value under "Credit Amount" or "Debit Amount" ---
        # Group 1: the amount with commas and optional decimal (e.g. "9,500.00")
        # Accounts for optional N or ₦ prefix variants that might appear
        amount_m = re.search(
            r"(?:Credit|Debit)\s+Amount\s+N?₦?\s*([\d,]+\.?\d*)",
            body, re.IGNORECASE
        )

        # --- Balance: captures the post-transaction balance ---
        # Group 1: the numeric balance (e.g. "10,256.12")
        # Preceded by "Account Balance:" and optional whitespace plus "N"
        balance_m = re.search(
            r"Account Balance[:\s]+N\s*([\d,]+\.?\d*)",
            body, re.IGNORECASE
        )

        # --- Account number: extracts the full 10+ digit account number ---
        # Group 1: the complete account number string
        # Only the last 4 digits are stored for security/privacy
        acct_m = re.search(
            r"Account Number[:\s]+([\d]{10,})",
            body, re.IGNORECASE
        )

        # --- Narration: captures the transaction description line ---
        # Group 1: everything after "Narration:" up to double newline, next capital-letter
        #   section header, or end of string. DOTALL allows matching across lines.
        # This captures entries like "MOBILE TRF TO MMF John Doe"
        narr_m = re.search(
            r"Narration[:\s]+(.+?)(?:\n\n|\n[A-Z]|$)",
            body, re.IGNORECASE | re.DOTALL
        )

        # --- Sender name: fallback narration when no explicit Narration field ---
        # Group 1: the sender name after optional "from" prefix
        #   e.g. "Sender's Name: from John Doe" → "John Doe"
        sender_m = re.search(
            r"Sender(?:'s)?\s+Name[:\s]+(?:from\s+)?(.+?)(?:\n|$)",
            body, re.IGNORECASE
        )

        # --- Date/time: captures the transaction timestamp ---
        # Group 1: date portion  — "22 May, 2026"
        # Group 2: time portion  — "10:28:56 AM"
        # Format: "<day> <month>, <year> | <HH:MM:SS AM/PM>"
        date_m = re.search(
            r"(\d{1,2}\s+[A-Za-z]+,\s+\d{4})\s*\|\s*(\d{1,2}:\d{2}:\d{2}\s*[AP]M)",
            body, re.IGNORECASE
        )

        # Abort if no amount found — this isn't a valid Moniepoint alert
        if not amount_m:
            return None

        # --- Narration extraction: prefer Narration field, fall back to sender name ---
        narration = ""
        if narr_m:
            # Collapse all whitespace (newlines, tabs) into single spaces
            narration = re.sub(r'\s+', ' ', narr_m.group(1)).strip()
        elif sender_m:
            narration = sender_m.group(1).strip()

        # --- Timestamp parsing: tries full month name first, then abbreviated month ---
        timestamp = None
        if date_m:
            date_str = f"{date_m.group(1)} {date_m.group(2).strip()}"
            try:
                # Attempt parse with full month name: "22 May, 2026 10:28:56 AM"
                timestamp = datetime.strptime(date_str, "%d %B, %Y %I:%M:%S %p")
            except Exception:
                try:
                    # Fallback to abbreviated month: "22 May, 2026 10:28:56 AM"
                    timestamp = datetime.strptime(date_str, "%d %b, %Y %I:%M:%S %p")
                except Exception:
                    pass

        # Only the last 4 digits of the account number are stored
        last4 = acct_m.group(1)[-4:] if acct_m else None

        return ParsedTransaction(
            bank          = self.BANK_NAME,
            tx_type       = tx_type,
            amount        = self._amount(amount_m.group(1)),
            balance       = self._amount(balance_m.group(1)) if balance_m else None,
            narration     = narration,
            account_last4 = last4,
            timestamp     = timestamp,
            category      = categorize(narration),
            raw_email     = body,
        )
