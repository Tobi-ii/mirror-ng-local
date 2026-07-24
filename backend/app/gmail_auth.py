"""
Gmail OAuth2 authentication and email fetching.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import base64
import email
from email.utils import parsedate_to_datetime

# Import parser
from .parsers import parse_email, ParsedTransaction, get_parser_for_sender

class GmailAuth:
    """Handle Gmail OAuth2 authentication"""
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    
    def __init__(self, credentials: Dict[str, Any]):
        """
        Initialize with user credentials
        
        Args:
            credentials: Dict containing token, refresh_token, token_uri, client_id, client_secret
        """
        self.creds = Credentials(
            token=credentials.get('token'),
            refresh_token=credentials.get('refresh_token'),
            token_uri=credentials.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=credentials.get('client_id'),
            client_secret=credentials.get('client_secret'),
            scopes=credentials.get('scopes', self.SCOPES)
        )
    
    def refresh_token_if_expired(self):
        """Refresh access token if expired"""
        if self.creds.expired and self.creds.refresh_token:
            self.creds.refresh(Request())
            return True
        return False
    
    def get_credentials_dict(self) -> Dict[str, Any]:
        """Get credentials as dict for storage"""
        return {
            'token': self.creds.token,
            'refresh_token': self.creds.refresh_token,
            'token_uri': self.creds.token_uri,
            'client_id': self.creds.client_id,
            'client_secret': self.creds.client_secret,
            'scopes': self.creds.scopes
        }


class GmailMirror:
    """Fetch and parse bank alert emails from Gmail"""
    
    def __init__(self, credentials: Dict[str, Any]):
        self.auth = GmailAuth(credentials)
        self.service = build('gmail', 'v1', credentials=self.auth.creds)
    
    def get_bank_alerts(self, max_results: int = 50, after_date: Optional[str] = None) -> List[ParsedTransaction]:
        """
        Fetch recent bank alert emails and parse them
        
        Args:
            max_results: Maximum number of emails to fetch
            after_date: Date string (YYYY/MM/DD) to filter emails after
        
        Returns:
            List of parsed Transaction objects
        """
        self.auth.refresh_token_if_expired()
        
        # Build query filter for Nigerian bank alerts
        bank_domains = [
            'from:sterling.ng', 'from:alerts@sterling.ng',
            'from:alat.ng', 'from:no-reply@alat.ng', 'from:wemabank.com', 'from:info@wemabank.com',
            'from:alert@kuda.com', 'from:kuda@kuda.com',
            'from:noreply@opay.com', 'from:opay@opay.com',
            'from:alerts@gtbank.com', 'from:noreply@gtbank.com',
            'from:no-reply@accessbank.com', 'from:alerts@accessbankplc.com',
            'from:alerts@ubagroup.com', 'from:firstbanknigeria.com',
            'from:moniepoint.com', 'from:no-reply@moniepoint.com',
            'from:palmpay.com', 'from:alerts@palmspay.com'
        ]
        
        query = f'({" OR ".join(bank_domains)}) AND (subject:Debit OR subject:Credit OR subject:Alert OR subject:Transaction OR subject:debit OR subject:credit)'
        
        # Add date filter if provided
        if after_date:
            query += f' after:{after_date}'
        
        try:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
        except Exception as e:
            logger.error(f"Gmail API error: {e}")
            return []
        
        transactions = []
        
        for msg in results.get('messages', []):
            tx = self._fetch_and_parse_email(msg['id'])
            if tx:
                transactions.append(tx)
        
        return transactions
    
    def _fetch_and_parse_email(self, msg_id: str) -> Optional[ParsedTransaction]:
        """Fetch a single email by ID and parse it"""
        try:
            msg_data = self.service.users().messages().get(
                userId='me',
                id=msg_id,
                format='full'
            ).execute()
            
            # Get headers
            headers = {h['name'].lower(): h['value'] for h in msg_data['payload'].get('headers', [])}
            
            sender = headers.get('from', '')
            subject = headers.get('subject', '')
            
            # Parse date
            date_str = headers.get('date', '')
            try:
                received_at = parsedate_to_datetime(date_str) if date_str else None
            except Exception:
                received_at = None
            
            if not received_at and 'internalDate' in msg_data:
                from datetime import datetime
                received_at = datetime.fromtimestamp(int(msg_data['internalDate']) / 1000)
            
            # Extract plain text body
            body = self._extract_body(msg_data['payload'])
            if not body:
                return None
            
            # Use the existing parser system
            parser = get_parser_for_sender(sender)
            if parser:
                tx = parser.parse(subject, body)
                if tx and not tx.timestamp:
                    tx.timestamp = received_at
                return tx
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching email {msg_id}: {e}")
            return None
    
    def _extract_body(self, payload: dict) -> Optional[str]:
        """Extract plain text body from email payload recursively"""
        if 'parts' in payload:
            for part in payload['parts']:
                body = self._extract_body(part)
                if body:
                    return body
            return None
        
        mime_type = payload.get('mimeType', '')
        if mime_type == 'text/plain':
            data = payload.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        elif mime_type == 'text/html':
            # Fallback to HTML if no plain text
            data = payload.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        
        return None
    
    def get_last_sync_date(self, user_id: str, db_connection) -> Optional[str]:
        """Get last sync timestamp for a user"""
        cursor = db_connection.execute('''
            SELECT MAX(timestamp) as last_tx 
            FROM transactions 
            WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        if row and row['last_tx']:
            # Return date part only for Gmail query
            return row['last_tx'].split('T')[0]
        return None