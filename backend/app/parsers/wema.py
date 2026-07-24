"""
Wema Bank email alert parser.

Handles credit ("has landed") and debit ("has been debited") alerts from
Wema Bank / ALAT. Supports OneBank transfers, NIP/IP/eTZ/TRF narration
prefixes, and deduplication of concatenated sender names (e.g. "PiggyVestPiggyVest").
"""

import re
import logging
from datetime import datetime
from typing import Optional
from .base import BankParser, ParsedTransaction, categorize

logger = logging.getLogger(__name__)

class WemaBankParser(BankParser):
    BANK_NAME      = "Wema Bank"
    # Match envelope sender e-mails used by Wema Bank / ALAT / BrevoSend
    SENDER_PATTERN = r"no-reply@alat\.ng|wemabank\.com|no-reply@11054915\.brevosend\.com"
    PROVIDES_BALANCE = True

    def parse(self, subject: str, body: str) -> Optional[ParsedTransaction]:
        """
        Parse a Wema Bank transaction alert email.

        Args:
            subject: Email subject line (used as fallback type detection).
            body: Full plain-text email body.

        Returns:
            ParsedTransaction with extracted fields, or None if no amount found.

        Examples:
            Credit:
                "NGN 2,500.00 has landed in account 0239****78
                 Note: NIP:FROMNAME-REF
                 Account Balance: 4,007.94 NGN"
            Debit:
                "NGN 3,000.00 has been debited from account 0239****78
                 Note: Transfer to Some Merchant
                 Account Balance: 1,007.94 NGN"
        """
        # Detect credit via "has landed" and debit via "has been debited"
        # Capture group 1: the monetary amount (e.g. "2,500.00")
        credit_m = re.search(r"NGN\s*([\d,]+\.?\d*)\s+has landed", body, re.IGNORECASE)
        debit_m  = re.search(r"NGN\s*([\d,]+\.?\d*)\s+has been debited", body, re.IGNORECASE)
        amount_m = credit_m or debit_m

        if not amount_m:
            # Broad fallback — grabs first NGN amount even without keyword
            amount_m = re.search(r"NGN\s*([\d,]+\.?\d*)", body, re.IGNORECASE)

        # Prefer keyword-based type; fall back to subject-line heuristics
        tx_type = "credit" if credit_m else ("debit" if debit_m else self._tx_type(subject, body))

        # Capture group 1: balance figure (e.g. "4,007.94"). Whitespace varies.
        balance_m = re.search(r"Account Balance[:\s]+([\d,]+\.?\d*)\s+NGN", body, re.IGNORECASE)

        # Grab the last 2 visible digits from a masked account like "0239****78"
        # Capture group 1: the final 2 digits, used as suffix to match records
        acct_m = re.search(r"Account No[:\s]+[\d\*]*([\d]{2})", body, re.IGNORECASE)

        # Group 1: "21-05-2026 19:24:52" in DD-MM-YYYY HH:MM:SS format
        date_m = re.search(r"Date and Time[:\s]+(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}:\d{2})", body, re.IGNORECASE)

        # Extract narration field starting after "Note:" until newline or "Account Balance"
        # DOTALL makes "." match newlines in case the note spans multiple lines
        narration_m = re.search(r"Note[:\s]+(.+?)(?:\n|Account Balance)", body, re.IGNORECASE | re.DOTALL)

        if not amount_m:
            return None

        narration = ""
        if narration_m:
            note_text = narration_m.group(1).strip()

            if tx_type == 'credit':
                # Strategy 1: extract sender name after "from" keyword
                from_match = re.search(r'\bfrom\s*([A-Za-z\s]+?)(?:\s+to\s|\s+FROM\s|$)', note_text, re.IGNORECASE)
                if from_match:
                    sender = from_match.group(1).strip()
                    # Remove any trailing "FROM" that got captured
                    sender = re.sub(r'\s+FROM\s*$', '', sender, flags=re.IGNORECASE).strip()
                    
                    # Deduplicate repeated names (e.g., "PiggyVestPiggyVest")
                    if len(sender) >= 6:
                        half = len(sender) // 2
                        if sender[:half] == sender[half:]:
                            sender = sender[:half]
                    if sender:
                        narration = sender

                # Strategy 2: fallback — parse structured prefix codes
                # IP:/NIP:/eTZ:/TRF:NAME-REF — capture name before the dash
                if not narration:
                    prefix_match = re.search(r'^(?:IP|NIP|eTZ|TRF):([^-]+)-', note_text, re.IGNORECASE)
                    if prefix_match:
                        narration = prefix_match.group(1).strip()
            else:
                # Debit: extract recipient or transaction type
                narration = note_text.strip()
                
                # Pattern 1: "Transfer to NAME" or "NIP TRANSFER TO NAME"
                to_match = re.search(r'(?:transfer\s+to|nip\s+transfer\s+to)\s+(.+?)(?:\s+from\s+|$)', narration, re.IGNORECASE)
                if to_match:
                    narration = to_match.group(1).strip()
                    # Remove trailing "FROM" if captured
                    narration = re.sub(r'\s+FROM\s*$', '', narration, flags=re.IGNORECASE).strip()
                else:
                    # Pattern 2: "POS Purchase on DATE@REF..." or "POS Transfer..."
                    pos_match = re.search(r'^(POS\s+(?:Purchase|Transfer))\s*(.*)', narration, re.IGNORECASE)
                    if pos_match:
                        pos_type = pos_match.group(1).strip()
                        pos_details = pos_match.group(2).strip()
                        # If there's extra details after POS type, keep them short
                        if pos_details:
                            # Remove "on DATE@REF" patterns
                            pos_details = re.sub(r'\s+on\s+\d{2}-\d{2}-\d{4}.*$', '', pos_details, flags=re.IGNORECASE)
                            narration = f"{pos_type} {pos_details}" if pos_details else pos_type
                        else:
                            narration = pos_type
                    else:
                        # Pattern 3: "ALAT NIP TRANSFER TO NAME"
                        alat_match = re.search(r'ALAT\s+NIP\s+TRANSFER\s+TO\s+(.+?)$', narration, re.IGNORECASE)
                        if alat_match:
                            narration = alat_match.group(1).strip()
                        else:
                            # Fallback: clean up common prefixes but keep meaningful text
                            narration = re.sub(r'^(Transfer|NIP|ALAT\s+NIP)\s+', '', narration, flags=re.IGNORECASE).strip()
                            # Remove "on DATE@REF" technical references
                            narration = re.sub(r'\s+on\s+\d{2}-\d{2}-\d{4}.*$', '', narration, flags=re.IGNORECASE).strip()
                
                # Final cleanup: remove any remaining "FROM" clauses
                narration = re.sub(r'\s+from\s+.+$', '', narration, flags=re.IGNORECASE).strip()
                
                # Truncate if too long
                if len(narration) > 40:
                    narration = narration[:40].rsplit(' ', 1)[0] + "..."

        timestamp = None
        if date_m:
            try:
                timestamp = datetime.strptime(date_m.group(1).strip(), "%d-%m-%Y %H:%M:%S")
            except Exception:
                # Fallback alternative date formats if primary parse fails
                timestamp = self._date(date_m.group(1).strip())

        return ParsedTransaction(
            bank          = self.BANK_NAME,
            tx_type       = tx_type,
            amount        = self._amount(amount_m.group(1)),
            balance       = self._amount(balance_m.group(1)) if balance_m else None,
            narration     = narration,
            account_last4 = acct_m.group(1) if acct_m else self._last4(body),
            timestamp     = timestamp,
            category      = categorize(narration),
            raw_email     = body,
        )
