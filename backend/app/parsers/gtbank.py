"""
gtbank.py — Guaranty Trust Bank (GTBank/GTCo) alert email parser

Handles DEBIT and CREDIT transaction notifications sent via
GeNS (GTBank electronic Notification Service).

Sender:  GeNS@gtbank.com

──────────────────────────────────────────────────────────
Handled GTBank alert formats:
──────────────────────────────────────────────────────────
1. Standard DEBIT alert — "a DEBIT transaction occurred on your account"
2. Standard CREDIT alert — "a CREDIT transaction occurred on your account"
3. Fallback: subject/body heuristic when the standard phrase is absent

──────────────────────────────────────────────────────────
Sample DEBIT alert (GTBank)
──────────────────────────────────────────────────────────
Subject: Transaction Notification

Dear [ACCOUNT HOLDER NAME]
Guaranty Trust Bank electronic Notification Service (GeNS)
We wish to inform you that a DEBIT transaction occurred
on your account with us.

Account Number   : ******[LAST4]
Transaction Location : [LOCATION CODE]
Description      : [DESCRIPTION]
Amount           : NGN [AMOUNT]
Value Date       : [YYYY-MM-DD]
Remarks          : [REMARKS]
Time of Transaction : [HH:MM:SS AM/PM]

Current Balance  : NGN [BALANCE]
Available Balance : NGN [BALANCE]
──────────────────────────────────────────────────────────
Note: GTBank uses a tab-separated table layout with
colons as separators. Amount has no decimal in some alerts.
Date and Time are on separate lines.
──────────────────────────────────────────────────────────
"""

import re
import logging
from datetime import datetime
from typing import Optional
from .base import BankParser, ParsedTransaction, categorize

logger = logging.getLogger(__name__)


class GTBankParser(BankParser):
    """
    Parser for Guaranty Trust Bank (GTBank) email alerts.

    Matches the GeNS notification format with tabular key:value
    fields.  Extracts tx_type, amount, balance, account_last4,
    narration (Description + Remarks), and timestamp (Value Date +
    Time of Transaction).  Delegates tx_type detection to the parent
    _tx_type fallback when the standard phrase is not present.
    """

    BANK_NAME        = "GTBank"
    SENDER_PATTERN   = r"GeNS@gtbank\.com|gtbank\.com"
    PROVIDES_BALANCE = True

    def parse(self, subject: str, body: str) -> Optional[ParsedTransaction]:
        """
        Extract GTBank transaction details from an email body.

        Args:
            subject: Email subject line (used in fallback tx_type detection).
            body:    Full email body text containing the GeNS alert table.

        Returns:
            ParsedTransaction with all matched fields, or None when
            the amount field (required) is missing.

        Example narrations parsed:
            "POS/WEB PURCHASE"        (from Description)
            "POS/WEB PURCHASE | Bill" (Description + Remarks concatenated)
        """

        # ── Transaction type ──────────────────────────────────────────
        # Match "a DEBIT transaction occurred" or "a CREDIT transaction occurred".
        # Group 1 captures the word DEBIT or CREDIT.
        type_m = re.search(
            r"a\s+(DEBIT|CREDIT)\s+transaction\s+occurred",
            body, re.IGNORECASE
        )
        if type_m:
            tx_type = type_m.group(1).lower()
        else:
            # Fallback: use parent heuristic (look for "debit"/"credit" in
            # subject line or body keywords) when the standard phrase is absent.
            tx_type = self._tx_type(subject, body)

        # ── Amount ────────────────────────────────────────────────────
        # Match "Amount : NGN 123,456.78".
        # Group 1 captures the numeric value (with optional commas and decimals).
        # The decimal part is optional because some GTBank alerts omit ".00".
        amount_m = re.search(
            r"Amount\s*:\s*NGN\s*([\d,]+\.?\d*)",
            body, re.IGNORECASE
        )

        # ── Balance ───────────────────────────────────────────────────
        # Match "Current Balance : NGN 123,456.78".
        # Group 1 captures the post-transaction balance.
        balance_m = re.search(
            r"Current Balance\s*:\s*NGN\s*([\d,]+\.?\d*)",
            body, re.IGNORECASE
        )

        # ── Account last 4 ───────────────────────────────────────────
        # Match "Account Number : ****1234".
        # \*+ skips the masked leading digits, ([0-9]{4}) captures the last 4.
        acct_m = re.search(
            r"Account Number\s*:\s*\*+([\d]{4})",
            body, re.IGNORECASE
        )

        # ── Description / narration ───────────────────────────────────
        # Match "Description : <text>". Non-greedy (.+?) stops at the next
        # newline to avoid consuming subsequent fields.
        narr_m = re.search(
            r"Description\s*:\s*(.+?)(?:\n|$)",
            body, re.IGNORECASE
        )
        # Match "Remarks : <text>" using the same non-greedy strategy.
        remarks_m = re.search(
            r"Remarks\s*:\s*(.+?)(?:\n|$)",
            body, re.IGNORECASE
        )

        # ── Date + Time ───────────────────────────────────────────────
        # GTBank uses ISO-8601 dates (YYYY-MM-DD) in the "Value Date" field.
        date_m = re.search(
            r"Value Date\s*:\s*(\d{4}-\d{2}-\d{2})",
            body, re.IGNORECASE
        )
        # Match "Time of Transaction : HH:MM:SS AM/PM".
        # Group 1 captures 12-hour clock with optional leading hour digit.
        time_m = re.search(
            r"Time of Transaction\s*:\s*(\d{1,2}:\d{2}:\d{2}\s*[AP]M)",
            body, re.IGNORECASE
        )

        # Amount is the only required field; bail if missing.
        if not amount_m:
            return None

        # ── Build narration from Description + Remarks ────────────────
        narration = ""
        if narr_m:
            narration = narr_m.group(1).strip()
        if remarks_m:
            remarks = remarks_m.group(1).strip()
            # Concatenate Remarks only when it adds new information (avoid
            # duplicates where Remarks simply echoes Description).
            if remarks and remarks.lower() not in ("", narration.lower()):
                narration = f"{narration} | {remarks}" if narration else remarks
        # Collapse any internal whitespace (tabs, multi-spaces) to single spaces.
        narration = re.sub(r'\s+', ' ', narration).strip()

        # ── Combine date and time ─────────────────────────────────────
        timestamp = None
        if date_m:
            date_str = date_m.group(1).strip()
            if time_m:
                time_str = time_m.group(1).strip()
                # Try full datetime first (date + 12-hour time).
                combined = f"{date_str} {time_str}"
                try:
                    timestamp = datetime.strptime(combined, "%Y-%m-%d %I:%M:%S %p")
                except Exception:
                    # Fallback to date-only if time fails to parse.
                    try:
                        timestamp = datetime.strptime(date_str, "%Y-%m-%d")
                    except Exception:
                        pass
            else:
                # No time field available — use date alone.
                try:
                    timestamp = datetime.strptime(date_str, "%Y-%m-%d")
                except Exception:
                    pass

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
