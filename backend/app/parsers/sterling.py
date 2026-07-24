"""
Parser for Sterling Bank email alert formats.

Handles the standard Sterling Bank debit/credit alert emails sent
from e-business@sterling.ng. Parses structured fields (Amount,
Current Balance, Account Number, Date, Transaction, Description)
from the email body. Also normalises OneBank Transfer narrations
that arrive as concatenated strings (e.g.
"OneBankTransferfromSENDERtoRECIPIENT").
"""

import re
import logging
from typing import Optional
from datetime import datetime
from .base import BankParser, ParsedTransaction, categorize

logger = logging.getLogger(__name__)

class SterlingBankParser(BankParser):
    """
    Parser for Sterling Bank transaction alert emails.

    Handles the structured email template where fields like Amount,
    Current Balance, Account Number, Date, Transaction, and Description
    are each on their own line prefixed by a label.
    """

    BANK_NAME      = "Sterling Bank"
    # Matches the sender address that triggers this parser
    SENDER_PATTERN = r"e-business@sterling\.ng"
    PROVIDES_BALANCE = False

    def parse(self, subject: str, body: str) -> Optional[ParsedTransaction]:
        """
        Extract a ParsedTransaction from a Sterling Bank alert email.

        Args:
            subject: Email subject line (not heavily used by this parser).
            body: Full email body containing labelled fields.

        Returns:
            ParsedTransaction if Amount field is found, else None.

        Narration formats handled:
            - Standard Description field from the email template.
            - OneBank Transfer from SENDER to RECIPIENT (concatenated).
            - Squished CamelCase names e.g. "OLAYEMIREBECCAADETUNJI".
            - Truncated names with trailing "...".
            - Names with " AND " clauses e.g. "BOVAS AND COMPANY LIMITED".
        """

        # Captures "Amount NGN2,100.00" — group(1) = "2,100.00"
        # Supports whole NGN amounts or amounts with decimal places.
        amount_m = re.search(r"Amount\s+NGN([\d,]+\.?\d*)", body, re.IGNORECASE)

        # Captures "Current Balance NGN0.00" — group(1) = balance string
        balance_m = re.search(r"Current Balance\s+NGN([\d,]+\.?\d*)", body, re.IGNORECASE)

        # Captures the last 4 digits from "Account Number *****95156"
        # Matches a mix of asterisks and digits, then extracts final 4 digits.
        acct_m = re.search(r"Account Number\s+[\*\d]*([\d]{4})", body, re.IGNORECASE)

        # Captures "Date 23/05/2026 6:21 AM" — group(1) = "DD/MM/YYYY H:MM AM/PM"
        date_m = re.search(r"Date\s+(\d{2}/\d{2}/\d{4}\s+\d+:\d{2}\s+[AP]M)", body, re.IGNORECASE)

        # Captures transaction direction: "Transaction DEBIT" or "Transaction CREDIT"
        type_m = re.search(r"Transaction\s+(DEBIT|CREDIT)", body, re.IGNORECASE)

        # Captures everything after "Description" until the next field starts.
        # Uses (?:\n|Amount) as a lookahead alternative to stop before "Amount".
        narration_m = re.search(r"Description\s+(.+?)(?:\n|Amount)", body, re.IGNORECASE | re.DOTALL)

        if not amount_m:
            return None

        tx_type = type_m.group(1).lower() if type_m else self._tx_type(subject, body)
        narration = narration_m.group(1).strip() if narration_m else ""

        # -- Narration normalisation for OneBank Transfer patterns --
        # The narration is already properly formatted with spaces:
        # "OneBank Transfer from SENDER to RECIPIENT"
        # We just need to extract the correct name based on tx_type
        
        normalized = narration.strip()
        
        # Pattern 1: "OneBank Transfer from X to Y" (with spaces)
        # Using \s+to\s+ ensures we don't split names like "OLORUNTOBILOBA"
        obo = re.search(
            r'OneBank\s+Transfer\s+from\s+(.+?)\s+to\s+(.+?)(?:\s*\(|$)',
            normalized, re.IGNORECASE
        )
        
        if obo:
            sender = obo.group(1).strip()
            recipient = obo.group(2).strip()
            
            # Remove trailing parenthetical like "(Paymentpoint)"
            recipient = re.sub(r'\s*\(.*?\)\s*$', '', recipient).strip()
            sender = re.sub(r'\s*\(.*?\)\s*$', '', sender).strip()
            
            # For debits, show recipient; for credits, show sender
            if tx_type == 'debit':
                narration = recipient
            else:
                narration = sender
        
        # Pattern 2: Concatenated format (fallback for older emails)
        # "OneBankTransferfromSENDERtoRECIPIENT" (no spaces)
        elif "OneBankTransfer" in normalized:
            # Find the LAST "to" between uppercase letters
            to_matches = list(re.finditer(r'(?<=[A-Z])to(?=[A-Z])', normalized))
            
            if to_matches:
                last_to = to_matches[-1]
                recipient_part = normalized[last_to.end():].strip()
                
                # Split CamelCase if needed
                if not recipient_part.isupper():
                    clean_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', recipient_part)
                    clean_name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', clean_name)
                    recipient_part = re.sub(r'\s+', ' ', clean_name).strip()
                
                # Remove parenthetical
                recipient_part = re.sub(r'\s*\(.*?\)\s*$', '', recipient_part).strip()
                
                if tx_type == 'debit':
                    narration = recipient_part
                else:
                    # Extract sender
                    sender_part = normalized[:last_to.start()].strip()
                    from_match = re.search(r'from([A-Z].+)$', sender_part, re.IGNORECASE)
                    if from_match:
                        sender = from_match.group(1).strip()
                        sender = re.sub(r'([a-z])([A-Z])', r'\1 \2', sender)
                        sender = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', sender)
                        narration = re.sub(r'\s+', ' ', sender).strip()
                    else:
                        narration = recipient_part
            
            # Handle truncation
            if " AND " in narration:
                narration = narration.split(" AND ")[0].strip()
            if "..." in narration:
                narration = narration.split("...")[0].strip()

        # Parse date from "DD/MM/YYYY H:MM AM/PM" format.
        timestamp = None
        if date_m:
            try:
                timestamp = datetime.strptime(date_m.group(1).strip(), "%d/%m/%Y %I:%M %p")
            except Exception:
                timestamp = self._date(date_m.group(1).strip())

        balance = self._amount(balance_m.group(1)) if balance_m else None
        if balance == 0.0:
            balance = None

        return ParsedTransaction(
            bank          = self.BANK_NAME,
            tx_type       = tx_type,
            amount        = self._amount(amount_m.group(1)),
            balance       = balance,
            narration     = narration,
            account_last4 = acct_m.group(1) if acct_m else None,
            timestamp     = timestamp,
            category      = categorize(narration),
            raw_email     = body,
        )
