"""
Stanbic IBTC Bank alert parser.

Handles email alerts from Stanbic IBTC (Nigeria) for debit/credit
transactions on personal and corporate accounts. Parses structured
HTML/plain-text e-alerts sent from stanbicibtc-e-alert@stanbicibtc.com.

Supported formats: "Debit Alert Details", "Credit Alert Details".
Extracts amount, balance, account number (last 4 digits), narration,
and transaction date/time from the alert body.
"""

import re
import logging
from datetime import datetime
from typing import Optional
from .base import BankParser, ParsedTransaction, categorize

logger = logging.getLogger(__name__)


class StanbicIBTCParser(BankParser):

    BANK_NAME        = "Stanbic IBTC"
    # Matches sender addresses for Stanbic IBTC e-alert emails.
    SENDER_PATTERN   = r"stanbicibtc-e-alert@stanbicibtc\.com|stanbicibtc"
    PROVIDES_BALANCE = True

    def parse(self, subject: str, body: str) -> Optional[ParsedTransaction]:
        """
        Parse a Stanbic IBTC email alert into a ParsedTransaction.

        Args:
            subject: Email subject line (unused in primary extraction).
            body: Full email body containing the transaction alert.

        Returns:
            ParsedTransaction with extracted fields, or None if no amount
            could be found (indicating an unrecognised or malformed alert).

        Examples:
            "Debit Alert Details" / "Credit Alert Details"
            Body sections:
              Amount NGN 5,000.00
              Current Balance NGN 150,000.00
              Account Number XXXX1234
              Description POS/WEB/***INTERNET PURCHASE***
              Transaction Date & Time 25-Mar-2025 14:30:00
        """
        # Transaction type
        # Look for "Debit Alert Details" or "Credit Alert Details" heading
        # in the body. Capture group 1 returns "debit" or "credit".
        type_m = re.search(r"(Debit|Credit)\s+alert\s+details", body, re.IGNORECASE)
        if type_m:
            tx_type = type_m.group(1).lower()
        else:
            # Fallback: infer type from subject line or other body cues.
            tx_type = self._tx_type(subject, body)

        # Amount
        # Extracts the numeric value after "Amount NGN". Handles commas
        # and optional decimal places. Group 1: the raw number string.
        amount_m = re.search(
            r"Amount\s+NGN\s*([\d,]+\.?\d*)",
            body, re.IGNORECASE
        )

        # Balance
        # Looks for "Current Balance NGN ...". Same capture strategy as
        # amount but under a different label. Group 1: raw number string.
        balance_m = re.search(
            r"Current Balance\s+NGN\s*([\d,]+\.?\d*)",
            body, re.IGNORECASE
        )

        # Account last 4
        # Finds "Account Number" followed by X/* masking then exactly 4
        # digits (e.g. "XXXX1234"). Group 1: the last 4 digits only.
        acct_m = re.search(
            r"Account Number\s+[Xx\*]+([\d]{4})",
            body, re.IGNORECASE
        )

        # Narration
        # Captures the transaction description following "Description".
        # Uses DOTALL so the dot matches newlines. Stops at a blank line,
        # "Transaction Reference", or "Account" heading.
        # Group 1: the narration text (possibly multi-line).
        narr_m = re.search(
            r"Description\s+(.+?)(?:\n\s*\n|\nTransaction Reference|\nAccount)",
            body, re.IGNORECASE | re.DOTALL
        )

        # Date
        # Matches "Transaction Date & Time" (or "Transaction Date Time")
        # followed by "DD-Mon-YYYY HH:MM:SS" format.
        # Group 1: the full date-time string, e.g. "25-Mar-2025 14:30:00".
        date_m = re.search(
            r"Transaction Date\s*&?\s*Time\s+(\d{2}-[A-Za-z]+-\d{4}\s+\d{2}:\d{2}:\d{2})",
            body, re.IGNORECASE
        )

        if not amount_m:
            return None

        # Collapse multi-line narration into a single space-separated
        # string, removing excessive whitespace while preserving words.
        narration = narr_m.group(1).strip() if narr_m else ""
        narration = re.sub(r'\s+', ' ', narration).strip()

        timestamp = None
        if date_m:
            date_str = date_m.group(1).strip().rstrip('.')
            try:
                # Stanbic uses abbreviated month names (e.g. "Mar").
                timestamp = datetime.strptime(date_str, "%d-%b-%Y %H:%M:%S")
            except Exception:
                # Fallback for non-standard date formats the base class
                # might handle (e.g. different locale or separator styles).
                timestamp = self._date(date_str)

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
