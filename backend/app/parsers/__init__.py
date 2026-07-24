"""
Parsers package — registry and dispatch layer for bank-specific email parsers.

Each bank module (sterling, wema, opay, etc.) exposes a parser class that
inherits from BankParser and defines a SENDER_PATTERN regex. The dispatch
functions in this module match an incoming sender email against those patterns
and return the correct parser instance to handle the message body.
"""

import re
import logging
from typing import List, Type, Optional
from .base import BankParser, ParsedTransaction
from .sterling import SterlingBankParser
from .wema import WemaBankParser
from .opay import OPayParser
from .stanbic import StanbicIBTCParser
from .stanchart import StandardCharteredParser
from .moniepoint import MoniepointParser
from .gtbank import GTBankParser

logger = logging.getLogger(__name__)

# Registration list: add a new parser class here to make it discoverable.
# Each class must have a SENDER_PATTERN regex class attribute. Order matters
# only when multiple patterns could match the same sender — first match wins.
PARSER_CLASSES: List[Type[BankParser]] = [
    SterlingBankParser,
    WemaBankParser,
    OPayParser,
    StanbicIBTCParser,
    StandardCharteredParser,
    MoniepointParser,
    GTBankParser,
]

def get_parser_for_sender(sender_email: str) -> Optional[BankParser]:
    """
    Match a sender email to a bank parser and return an instance.

    Handles RFC 5322 display-name formats (e.g. "Bank Name <user@bank.com>")
    by stripping the angle-bracket portion before matching.

    Args:
        sender_email: Raw From header value, possibly including display name.

    Returns:
        An instance of the matching BankParser subclass, or None if no
        SENDER_PATTERN in PARSER_CLASSES matches the extracted email.

    Examples:
        >>> parser = get_parser_for_sender("alert@sterlingbank.com.ng")
        >>> type(parser).__name__
        'SterlingBankParser'

        >>> get_parser_for_sender("unknown@example.com") is None
        True
    """
    # Strip display-name wrapper so we only match against the bare addr-spec.
    # RFC 5322 allows "John Doe <john@example.com>" — we need the <...> part.
    match = re.search(r'<([^>]+)>', sender_email)
    clean_email = match.group(1).strip() if match else sender_email.strip()

    logger.debug(f"🔍 Matching sender: '{sender_email}' → clean: '{clean_email}'")

    # Walk PARSER_CLASSES in registration order; first regex match wins.
    for ParserClass in PARSER_CLASSES:
        if re.search(ParserClass.SENDER_PATTERN, clean_email, re.IGNORECASE):
            logger.debug(f"✅ Matched parser: {ParserClass.__name__}")
            return ParserClass()

    logger.debug(f"❌ No parser matched for: '{clean_email}'")
    return None

def parse_email(sender_email: str, subject: str, body: str) -> Optional[ParsedTransaction]:
    """
    Convenience: resolve a parser for *sender_email* and immediately parse.

    Combines get_parser_for_sender and parser.parse into a single call.
    Returns None when no parser matches or when parsing fails.

    Args:
        sender_email: Raw From header value.
        subject: Email subject line.
        body: Email body text (plain text preferred).

    Returns:
        A ParsedTransaction if a parser matched and succeeded, else None.

    Examples:
        >>> result = parse_email("no-reply@gtbank.com", "Debit Alert", "NGN 5000")
        >>> result.amount
        5000.0
    """
    parser = get_parser_for_sender(sender_email)
    if not parser:
        return None
    return parser.parse(subject, body)

def get_all_sender_patterns() -> List[str]:
    """Return the SENDER_PATTERN regex strings for every registered parser.

    Useful for dynamic configuration, e.g. building a combined filter
    regex or displaying supported senders in a settings UI.
    """
    return [p.SENDER_PATTERN for p in PARSER_CLASSES]

__all__ = [
    "BankParser",
    "ParsedTransaction",
    "PARSER_CLASSES",
    "SterlingBankParser",
    "WemaBankParser",
    "OPayParser",
    "StanbicIBTCParser",
    "StandardCharteredParser",
    "MoniepointParser",
    "GTBankParser",
    "get_parser_for_sender",
    "parse_email",
    "get_all_sender_patterns",
]
