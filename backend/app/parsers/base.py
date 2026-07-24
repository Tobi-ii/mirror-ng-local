"""
Base parser framework for bank email transaction parsing.

Architecture:
- ParsedTransaction: dataclass holding a single parsed transaction's fields.
- BankParser: abstract base class. Subclasses implement parse() to extract
  transactions from bank-specific email formats.
- categorize(): standalone helper that classifies narration text into a category.

Extend by subclassing BankParser, setting BANK_NAME, and overriding parse().
"""
import re
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ParsedTransaction:
    """Normalised representation of a single financial transaction.

    Fields mirror the unified schema used by downstream processors and storage.
    """
    bank: str
    """Name of the originating bank (e.g. "GTBank", "Access Bank")."""
    tx_type: str
    """Either "debit" or "credit". Determined heuristically from email content."""
    amount: float
    """Transaction amount as a float. Commas stripped before conversion."""
    balance: Optional[float]
    """Post-transaction account balance, if available in the email."""
    narration: str
    """Free-text description of the transaction (merchant, reference, etc.)."""
    account_last4: Optional[str]
    """Last four digits of the affected account, if present."""
    timestamp: datetime
    """Parsed datetime of the transaction from the email."""
    category: str
    """High-level grouping derived from narration (e.g. "Transfer", "Utilities")."""
    raw_email: str
    """Original unmodified email body for audit / reprocessing."""

    def to_dict(self):
        """Serialise to a JSON-safe dict, converting datetime to ISO string."""
        return {
            "id": getattr(self, 'id', None),
            "bank": self.bank,
            "tx_type": self.tx_type,
            "amount": self.amount,
            "balance": self.balance,
            "narration": self.narration,
            "account_last4": self.account_last4,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "category": self.category,
        }

class BankParser:
    """Base class for all bank parsers.

    Subclasses MUST override :meth:`parse`. They may also override
    BANK_NAME and SENDER_PATTERN to match bank-specific identifiers.
    """
    BANK_NAME = "Generic Bank"
    """Display name used when the bank cannot be identified."""
    SENDER_PATTERN = r"@"
    """Regex matched against the sender address to identify this bank."""

    def _amount(self, val: str) -> Optional[float]:
        """Convert a numeric string to float, handling thousand separators.

        Args:
            val: Raw amount string (e.g. "1,500.75").

        Returns:
            Float value, or None if the input is empty or unparseable.
        """
        if not val: return None
        try:
            return float(val.replace(',', ''))
        except ValueError:
            return None

    def _date(self, date_str: str) -> Optional[datetime]:
        """Parse a date string against several common Nigerian bank formats.

        Tries formats in order and returns the first successful parse.

        Args:
            date_str: Raw date string from the email.

        Returns:
            A datetime object, or None if no format matched.
        """
        if not date_str: return None
        date_str = re.sub(r'\s+', ' ', date_str.strip())
        formats = [ "%d/%m/%Y %I:%M %p", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %I:%M %p", "%d-%m-%Y %H:%M:%S",]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def _tx_type(self, subject: str, body: str) -> str:
        """Determine transaction type by keyword heuristics on subject + body.

        Args:
            subject: Email subject line.
            body: Email body text.

        Returns:
            "debit" if a debit-related keyword is found, else "credit".
        """
        text = (subject + " " + body).lower()
        if any(w in text for w in ['debit', 'money out', 'sent']): return 'debit'
        return 'credit'

    def parse(self, subject: str, body: str) -> Optional[ParsedTransaction]:
        """Extract a parsed transaction from a bank-specific email.

        This is the main extension point — every subclass must implement it.

        Args:
            subject: Raw email subject line.
            body: Raw email body.

        Returns:
            A ParsedTransaction instance, or None if the email could not be
            matched / parsed successfully.
        """
        raise NotImplementedError("Subclasses must implement parse()")

def categorize(narration: str) -> str:
    """Classify a narration string into a high-level spending category.

    Args:
        narration: Transaction description text.

    Returns:
        One of "Utilities", "Transfer", or "General" as a fallback.
    """
    n = narration.lower()
    if any(w in n for w in ['airtime', 'data', 'mtn']): return 'Utilities'
    if any(w in n for w in ['transfer', 'nip']): return 'Transfer'
    return 'General'
