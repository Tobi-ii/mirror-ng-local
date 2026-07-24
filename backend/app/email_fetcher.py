"""
DEPRECATED — This file is a duplicate of the EmailFetcher class defined inside main.py.
The main.py version is the one actually used in production (see /api/sync endpoint).
This file is kept only because test_yahoo_fetcher.py and test_imap_simple.py import from it.

If you're adding a new feature, add it to the EmailFetcher class in main.py instead.
"""

import warnings
warnings.warn("email_fetcher.py is deprecated. Use the EmailFetcher class in main.py instead.", DeprecationWarning, stacklevel=2)
import imaplib
import email
import re
import quopri
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
from email.policy import default

# Import Gmail support
from .gmail_auth import GmailMirror
from .parsers import parse_email, ParsedTransaction

logger = logging.getLogger(__name__)

class YahooIMAPFetcher:
    def __init__(self, email_address: str, app_password: str):
        self.email_address = email_address
        self.app_password = app_password
        self.server = "imap.mail.yahoo.com"
        self.port = 993

    def connect(self):
        try:
            mail = imaplib.IMAP4_SSL(self.server, self.port)
            mail.login(self.email_address, self.app_password)
            mail.select("INBOX")
            logger.info(f"✅ Connected to Yahoo IMAP: {self.email_address}")
            return mail
        except imaplib.IMAP4.error as e:
            raise ValueError(f"Invalid Yahoo credentials: {e}")
        except Exception as e:
            raise

    def fetch_alerts(self, sender_patterns: List[str], limit: int = 100,
                     since_date: Optional[str] = None,
                     until_date: Optional[str] = None) -> List[Dict[str, Any]]:
        mail = self.connect()
        try:
            # Build search criteria
            if since_date:
                d_since = datetime.strptime(since_date, "%Y-%m-%d")
                since_imap = d_since.strftime("%d-%b-%Y")
                if until_date:
                    d_until = datetime.strptime(until_date, "%Y-%m-%d")
                    # Add one day to include the end date
                    from datetime import timedelta
                    d_until = d_until + timedelta(days=1)
                    until_imap = d_until.strftime("%d-%b-%Y")
                    search_criteria = f'SINCE {since_imap} BEFORE {until_imap}'
                else:
                    search_criteria = f'SINCE {since_imap}'
            else:
                search_criteria = "ALL"

            logger.info(f"🔍 Yahoo IMAP Search: {search_criteria}")
            status, messages = mail.search(None, search_criteria)

            if status != "OK" or not messages[0]:
                logger.warning(f"No messages found")
                return []

            message_ids = messages[0].split()
            logger.info(f"📬 Found {len(message_ids)} total emails")

            # Limit to recent messages
            if len(message_ids) > limit:
                message_ids = message_ids[-limit:]

            bank_emails = []

            for msg_id in reversed(message_ids):
                try:
                    status, msg_data = mail.fetch(msg_id, "(RFC822)")
                    if status != "OK":
                        continue

                    msg = email.message_from_bytes(msg_data[0][1], policy=default)
                    sender = msg.get("From", "")
                    date_str = msg.get("Date", "")

                    # Check if from bank domain
                    if any(re.search(pattern, sender, re.IGNORECASE) for pattern in sender_patterns):
                        bank_emails.append({
                            "subject": msg.get("Subject", ""),
                            "from": sender,
                            "raw": self._get_email_body(msg),
                            "date": date_str,
                            "message_id": msg.get("Message-ID", "")
                        })
                except Exception as e:
                    logger.debug(f"Skipping email {msg_id}: {e}")
                    continue

            logger.info(f"📥 Found {len(bank_emails)} bank alert emails")
            return bank_emails
        finally:
            mail.logout()

    def _get_email_body(self, msg) -> str:
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        return self._decode_and_clean(part)
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        return self._decode_and_clean(part, is_html=True)
            else:
                return self._decode_and_clean(msg, msg.get_content_type() == "text/html")
        except Exception as e:
            logger.warning(f"Failed to extract email body: {e}")
        return ""

    def _decode_and_clean(self, part, is_html: bool = False) -> str:
        try:
            payload = part.get_payload(decode=True)
            if not payload:
                payload = part.get_payload()
                if isinstance(payload, list):
                    payload = payload[0] if payload else ""

            if isinstance(payload, bytes):
                charset = part.get_content_charset() or 'utf-8'
                text = payload.decode(charset, errors='ignore')
            else:
                text = str(payload)

            # Decode quoted-printable
            if '=3D' in text or '=20' in text:
                try:
                    text = quopri.decodestring(text.encode('utf-8')).decode('utf-8', errors='ignore')
                except Exception:
                    pass

            if is_html:
                text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', text)
                html_entities = {
                    '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
                    '&quot;': '"', '&#39;': "'", '&#x27;': "'", '&#x2F;': '/'
                }
                for entity, char in html_entities.items():
                    text = text.replace(entity, char)

            return re.sub(r'\s+', ' ', text).strip()
        except Exception as e:
            logger.warning(f"Failed to decode: {e}")
            return ""


class GmailAPIFetcher:
    """Fetch emails using Gmail API"""
    
    def __init__(self, credentials: Dict[str, Any]):
        self.credentials = credentials
        self.gmail_mirror = GmailMirror(credentials)
    
    def fetch_alerts(self, sender_patterns: List[str], limit: int = 100,
                     since_date: Optional[str] = None,
                     until_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch bank alerts using Gmail API
        
        Args:
            sender_patterns: List of patterns to match senders (not used directly, GmailMirror has its own)
            limit: Maximum number of emails to fetch
            since_date: ISO format date string (YYYY-MM-DD)
            until_date: ISO format date string (not used in Gmail API directly)
        """
        # Parse since_date for Gmail API
        after_date = since_date.replace('-', '/') if since_date else None
        
        # Fetch transactions using GmailMirror
        transactions = self.gmail_mirror.get_bank_alerts(
            max_results=limit,
            after_date=after_date
        )
        
        # Convert Transaction objects to dict format compatible with existing code
        results = []
        for tx in transactions:
            results.append({
                "subject": f"{tx.tx_type.upper()} Alert",  # Approximate subject
                "from": f"{tx.bank}",  # Approximate sender
                "raw": f"{tx.narration}",  # Body text
                "date": tx.timestamp.isoformat() if tx.timestamp else "",
                "message_id": f"gmail_{tx.id}" if hasattr(tx, 'id') else ""
            })
        
        logger.info(f"📥 Gmail API: Found {len(results)} bank alert emails")
        return results


class UnifiedEmailFetcher:
    """Unified fetcher that handles both Yahoo IMAP and Gmail API"""
    
    def __init__(self, email_address: str, provider: str = 'yahoo', 
                 app_password: Optional[str] = None,
                 credentials: Optional[Dict[str, Any]] = None):
        """
        Initialize the appropriate fetcher based on provider
        
        Args:
            email_address: User's email address
            provider: 'yahoo', 'gmail', or 'gmail_api'
            app_password: App password for Yahoo or Gmail app password
            credentials: OAuth credentials dict for Gmail API
        """
        self.email_address = email_address
        self.provider = provider
        
        if provider == 'yahoo':
            if not app_password:
                raise ValueError("App password required for Yahoo")
            self._fetcher = YahooIMAPFetcher(email_address, app_password)
        elif provider == 'gmail_api':
            if not credentials:
                raise ValueError("OAuth credentials required for Gmail API")
            self._fetcher = GmailAPIFetcher(credentials)
        elif provider == 'gmail':
            # Gmail with app password (IMAP fallback)
            if not app_password:
                raise ValueError("App password required for Gmail IMAP")
            self._fetcher = YahooIMAPFetcher(email_address, app_password)
            # Override server for Gmail
            self._fetcher.server = "imap.gmail.com"
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    def fetch_alerts(self, sender_patterns: List[str], limit: int = 100,
                     since_date: Optional[str] = None,
                     until_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch bank alerts using the appropriate method"""
        return self._fetcher.fetch_alerts(sender_patterns, limit, since_date, until_date)