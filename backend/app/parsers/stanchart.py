"""
stanchart.py — Standard Chartered Bank Nigeria alert email parser

Sender:  alerts.nigeria@sc.com

──────────────────────────────────────────────────────────
Sample DEBIT alert (Standard Chartered)
──────────────────────────────────────────────────────────
Subject: Standard Chartered: Transaction Alert

Dear Customer,

Email Alerts Summary

Banking Transaction
Debit Alert! Acct:xxxxxx[LAST4], Amt:NGN120000.00,
Desc:[NARRATION], Date:2026-02-06, Bal:NGN0.32

──────────────────────────────────────────────────────────
Note: Standard Chartered packs all transaction fields
into a single comma-separated line. No multiline labels.

Handled formats:
  - Debit Alert! / Credit Alert! inline format (single-line fields)
  - Amount in NGN (e.g. NGN120000.00)
  - Date in ISO format (YYYY-MM-DD)
  - Balance included inline
──────────────────────────────────────────────────────────
"""

import re
import logging
from datetime import datetime
from typing import Optional
from .base import BankParser, ParsedTransaction, categorize

logger = logging.getLogger(__name__)


class StandardCharteredParser(BankParser):
    """Parses single-line Standard Chartered email alerts.

    Standard Chartered does not use multi-line labels; all fields
    (acct, amount, desc, date, balance) appear on one comma-separated line
    prefixed by "Debit Alert!" or "Credit Alert!".

    Args:
        subject: Email subject line.
        body: Email body text.

    Returns:
        ParsedTransaction with extracted fields, or None if not a valid alert.

    Example narration formats parsed:
        - "POS Purchase 12345678 NGN 5000.00" → category: POS
        - "TRF TO 0123456789 USER NAME" → category: Transfer
        - "ATM WITHDRAWAL 001234" → category: ATM
        - "WEB PAYMENT TO MERCHANT" → category: Online
        - "SALARY WAGES" → category: Salary
        - "FEE: VAT ON CHARGES" → category: Charges
    """

    BANK_NAME        = "Standard Chartered"
    # Matches sender address pattern for alert routing
    SENDER_PATTERN   = r"alerts\.nigeria@sc\.com|sc\.com"
    PROVIDES_BALANCE = True

    def parse(self, subject: str, body: str) -> Optional[ParsedTransaction]:

        # ── Transaction type ──────────────────────────────────────────────
        # "Debit Alert!" or "Credit Alert!" — these always appear at line start
        type_m = re.search(r"(Debit|Credit)\s+Alert!", body, re.IGNORECASE)
        if type_m:
            tx_type = type_m.group(1).lower()
        else:
            tx_type = self._tx_type(subject, body)

        # ── The core alert line ───────────────────────────────────────────
        # Captures everything from "Debit/Credit Alert!" to end-of-line,
        # which is the entire comma-separated transaction payload.
        alert_line = ""
        alert_m = re.search(
            r"((?:Debit|Credit)\s+Alert!.+?)(?:\n|$)",
            body, re.IGNORECASE
        )
        if alert_m:
            alert_line = alert_m.group(1)

        # ── Amount (NGN only) ─────────────────────────────────────────────
        # Pattern: "Amt:NGN" followed by digits with optional comma separators
        # and decimal part.  Captures the numeric value (excluding "NGN").
        amount_m = re.search(r"Amt:NGN([\d,]+\.?\d*)", alert_line or body, re.IGNORECASE)

        # ── Balance ───────────────────────────────────────────────────────
        # Same structure as amount: "Bal:NGN<number>".
        # Falls back to full body if alert_line is empty.
        balance_m = re.search(r"Bal:NGN([\d,]+\.?\d*)", alert_line or body, re.IGNORECASE)

        # ── Account last 4 digits ─────────────────────────────────────────
        # Account field is "Acct:xxxxxx<LAST4>" — mask characters may be X or *.
        # Captures exactly the final 4 digits.
        acct_m = re.search(r"Acct:[Xx\*]+([\d]{4})", alert_line or body, re.IGNORECASE)

        # ── Narration (Desc field) ────────────────────────────────────────
        # Description is bounded by "Desc:" prefix and either a comma followed
        # by "Date:" or line-end.  Uses non-greedy match to avoid over-capturing.
        narr_m = re.search(r"Desc:(.+?)(?:,\s*Date:|$)", alert_line or body, re.IGNORECASE)

        # ── Date (ISO format) ─────────────────────────────────────────────
        # Strict YYYY-MM-DD format — Standard Chartered uses ISO dates.
        date_m = re.search(r"Date:(\d{4}-\d{2}-\d{2})", alert_line or body, re.IGNORECASE)

        if not amount_m:
            return None

        # Normalize narration: strip leading/trailing whitespace and collapse
        # internal multiple spaces into a single space.
        narration = narr_m.group(1).strip() if narr_m else ""
        narration = re.sub(r'\s+', ' ', narration).strip()

        timestamp = None
        if date_m:
            try:
                timestamp = datetime.strptime(date_m.group(1).strip(), "%Y-%m-%d")
            except Exception:
                timestamp = self._date(date_m.group(1).strip())

        return ParsedTransaction(
            bank          = self.BANK_NAME,
            tx_type       = tx_type,
            amount        = self._amount(amount_m.group(1)),
            balance       = self._amount(balance_m.group(1)) if balance_m else None,
            narration     = narration,
            account_last4 = acct_m.group(1) if acct_m else None,
            timestamp     = timestamp,
            category      = categorize(narration),
            raw_email     = body,
        )
