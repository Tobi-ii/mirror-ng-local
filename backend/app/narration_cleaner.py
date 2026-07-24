"""
Narration cleaning utilities for Mirror.ng.

Extracts meaningful names/merchants from verbose bank alert narrations.
Bank-specific logic lives here to keep main.py focused on API routes.
"""

import re
import logging

logger = logging.getLogger(__name__)


def clean_narration(narration: str, bank: str) -> str:
    """
    Extract meaningful name from verbose bank narrations.
    
    Args:
        narration: Raw narration from bank parser
        bank: Bank name (e.g., "Sterling Bank", "Wema Bank")
    
    Returns:
        Cleaned narration (usually recipient/sender name)
    """
    if not narration or not narration.strip():
        return "Unknown Transaction"
    
    text = narration.strip()
    
    # Airtime purchases: "[REF] | Airtime purchase for [PHONE]"
    airtime_match = re.search(r'airtime purchase for\s+(\d+)', text, re.IGNORECASE)
    if airtime_match:
        return f"Airtime {airtime_match.group(1)}"
    
    # Sterling Bank - Credit: "BANKNIP From [REF1] [REF2] PAYREF: [REF] SENDER: [SENDER] REMARK: ..."
    if bank == "Sterling Bank" and "BANKNIP" in text.upper():
        sender_match = re.search(r'SENDER:\s*(.+?)(?:\s+REMARK:|$)', text, re.IGNORECASE)
        if sender_match:
            sender = sender_match.group(1).strip()
            sender = re.sub(r'\s+', ' ', sender)
            return sender
    
    # Sterling Bank - Debit: "OneBank Transfer from [SENDER] to [RECIPIENT]"
    if bank == "Sterling Bank" and ("OneBank Transfer" in text or "OneBankTransfer" in text):
        recipient_match = re.search(r'\bto\s+(.+?)(?:\s+remark|\s+date|\s+value|$)', text, re.IGNORECASE)
        if recipient_match:
            recipient = recipient_match.group(1).strip()
            recipient = re.sub(r'\s+', ' ', recipient)
            if " AND " in recipient:
                recipient = recipient.split(" AND ")[0].strip()
            if "..." in recipient:
                recipient = recipient.split("...")[0].strip()
            return recipient
    
    # Wema Bank - Credit/Debit
    if bank in ("Wema Bank", "Wema (ALAT)", "ALAT"):
        # Pattern 1: "NIP:[NAME]-Transfer from[SENDER]" or "IP:[NAME]-OneBank Transfer from [SENDER] to [RECIPIENT]"
        if "Transfer from" in text:
            # Check if there's a "to" after "Transfer from" (outgoing transfer)
            to_match = re.search(r'Transfer from.*?\bto\s+(.+?)$', text, re.IGNORECASE)
            if to_match:
                # Outgoing: extract recipient
                recipient = to_match.group(1).strip()
                recipient = re.sub(r'\s+', ' ', recipient)
                return recipient
            else:
                # Incoming: extract sender after "Transfer from"
                sender_match = re.search(r'Transfer from\s*(.+?)$', text, re.IGNORECASE)
                if sender_match:
                    sender = sender_match.group(1).strip()
                    sender = re.sub(r'\s+', ' ', sender)
                    if not sender:
                        # No sender after "Transfer from", check prefix
                        prefix_match = re.search(r'^(?:NIP|IP):(.+?)-', text)
                        if prefix_match:
                            return prefix_match.group(1).strip()
                    return sender
        
        # Pattern 2: "[PREFIX] ALAT NIP TRANSFER TO [RECIPIENT] FROM [SENDER]" (Wema debit)
        elif "TRANSFER TO" in text.upper() and "FROM" in text.upper():
            sender_match = re.search(r'\bFROM\s+(.+?)$', text, re.IGNORECASE)
            if sender_match:
                sender = sender_match.group(1).strip()
                sender = re.sub(r'\s+', ' ', sender)
                return sender
    
    # OPay and others: Already clean, return as-is
    return text
