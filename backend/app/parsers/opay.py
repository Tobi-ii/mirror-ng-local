"""
OPay email transaction parser.

Handles OPay Nigeria alerts: credit notifications ("credited"), debit
confirmations ("transfer of ₦X is successful"), and general transaction
narrations extracted from OPay's no-reply@opay-nigeria.com emails.
"""

import re
import logging
from datetime import datetime
from typing import Optional
from .base import BankParser, ParsedTransaction, categorize

logger = logging.getLogger(__name__)

class OPayParser(BankParser):
    """
    Parser for OPay Nigeria financial alerts.

    Supports these notification formats:
      - "Your transfer of ₦2,500.00 is successful" (outgoing / debit)
      - "₦2,500.00 has been credited" (incoming / credit)
      - Narration with recipient name via "Name: ... Bank:"
      - "available balance is ₦..." or "available balance of N..."
      - "Transaction Date: May 21st, 2026 19:24:36" (with ordinal suffix)
      - "Amount: ₦..." as fallback when primary patterns miss
    """

    BANK_NAME      = "OPay"
    SENDER_PATTERN = r"no-reply@opay-nigeria\.com|opay"
    PROVIDES_BALANCE = True

    def parse(self, subject: str, body: str) -> Optional[ParsedTransaction]:
        """
        Extract transaction data from an OPay email body.

        Args:
            subject: Email subject line (unused by this parser).
            body:    Full email body text.

        Returns:
            ParsedTransaction if an amount is found, else None.

        Examples:
            Body: "Your transfer of ₦2,500.00 is successful ..."
            Body: "₦5,000.00 has been credited to your wallet ..."
            Body: "Amount: ₦1,200.00 ... available balance is ₦3,400.00"
        """
        # "transfer of ₦2,500.00" — outgoing debit.  Group-1 captures the
        # numeric portion (with commas and optional decimals).
        transfer_m = re.search(r"transfer of ₦([\d,]+\.?\d*)", body, re.IGNORECASE)
        # "₦2,500.00 has been credited" — incoming credit.
        credit_m   = re.search(r"₦([\d,]+\.?\d*)\s+has been credited", body, re.IGNORECASE)
        amount_m   = transfer_m or credit_m

        if not amount_m:
            # Fallback: "Amount: ₦..." for generic-format OPay emails.
            amount_m = re.search(r"Amount[:\s]+₦([\d,]+\.?\d*)", body, re.IGNORECASE)

        # Prefer keyword-based type detection; fall back to heuristic scan.
        tx_type = "debit" if transfer_m else ("credit" if credit_m else self._tx_type(subject, body))

        # Matches OPay's two balance-phrasing variants as of 2025+.
        # Group-1: the balance amount (e.g. "12,730.44").
        balance_m = re.search(r"available balance (?:is|of)\s*[₦N]([\d,]+\.?\d*)", body, re.IGNORECASE)

        # "Transaction Date: May 21st, 2026 19:24:36"
        # Group-1: full date-time string including the ordinal suffix on the day.
        date_m = re.search(
            r"Transaction Date[:\s]+([A-Za-z]+ \d+\w*, \d{4} \d{2}:\d{2}:\d{2})",
            body, re.IGNORECASE
        )

        # Extracts the payee name between "Name:" and the next "Bank:" marker.
        # Group-1: the cleaned recipient name (single line, trimmed).
        narration_m = re.search(r"Name[:\s]+(.+?)(?:\n|Bank:)", body, re.IGNORECASE | re.DOTALL)

        if not amount_m:
            return None

        narration = narration_m.group(1).strip() if narration_m else ""

        timestamp = None
        if date_m:
            # Strip English ordinal suffixes (st/nd/rd/th) so strptime can
            # parse the day number (e.g. "21st" → "21").
            date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_m.group(1))
            try:
                timestamp = datetime.strptime(date_str.strip(), "%B %d, %Y %H:%M:%S")
            except ValueError:
                try:
                    # Some OPay emails abbreviate the month (e.g. "Jun").
                    timestamp = datetime.strptime(date_str.strip(), "%b %d, %Y %H:%M:%S")
                except Exception:
                    pass

        return ParsedTransaction(
            bank          = self.BANK_NAME,
            tx_type       = tx_type,
            amount        = self._amount(amount_m.group(1)),
            balance       = self._amount(balance_m.group(1)) if balance_m else None,
            narration     = narration,
            # OPay emails show the *destination* account number, not the
            # user's own OPay wallet number.  Deliberately leaving this
            # blank forces the onboarding gaps modal to ask the user for
            # their OPay account's last 4 digits manually.
            account_last4 = None,
            timestamp     = timestamp,
            category      = categorize(narration),
            raw_email     = body,
        )
