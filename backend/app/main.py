"""
Mirror.ng FastAPI Main Application
Supports: Yahoo IMAP, Gmail OAuth2, Gmail App Password
Nigerian Bank Alert Aggregator with ML Insights
"""

from fastapi import FastAPI, HTTPException, Request, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
import os
import logging
import re
import secrets
import imaplib
import email
import quopri
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable
import sqlite3
from dotenv import load_dotenv
import email.utils as email_utils
from email.policy import default
from pydantic import BaseModel as PydanticBase
import asyncio
import uuid
import hashlib
import threading
import time

# OAuth imports
from authlib.integrations.starlette_client import OAuth
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
import base64

# Auth
from .auth import create_access_token, decode_access_token, get_current_user_id, verify_admin, encrypt_email_password, decrypt_email_password

# Core Modules
from .database import get_db, init_db
from .balance_manager import BalanceManager
from .parsers import get_parser_for_sender, PARSER_CLASSES

# Agent / LLM
from .agent import run_agent, _pending_bulk_updates
from .intent_agent import run_intent_agent
from .temporal import get_agent_temporal_context

# ML Modules
from .ml.classifier import predict_category, train_classifier
from .ml.anomaly import detect_anomalies
from .ml.forecaster import weekly_spend_forecast
from .ml.merchant import get_top_merchants
from .ml.recurring import detect_recurring

# Narration Cleaner
from .narration_cleaner import clean_narration

# Models
from .models import (
    SyncRequest,
    InitialBalanceRequest,
    ManualAdjustRequest,
    AliasRequest,
    AgentChatRequest,
    CloudSyncToggle,
    DataExportResponse,
    DataImportRequest,
    OnboardingDatesRequest,
    OpeningBalanceItem
)

load_dotenv()

# Environment-aware cookie security — disabled for local dev (HTTP)
COOKIE_SECURE = os.getenv("ENV", "development") == "production"
HTTPS_ONLY = os.getenv("HTTPS_ONLY", "false").lower() == "true"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── In-memory rate limiter ─────────────────────────────────────────
from collections import defaultdict
import time

_rate_limit_store = defaultdict(list)

# Background sync job store (in-memory, ephemeral)
# Keyed by job_id (UUID), each entry tracks progress, status, and result.
# Expired entries are pruned every 5 minutes by a background task.
_sync_jobs: Dict[str, Dict] = {}
_sync_jobs_lock = threading.Lock()

def check_rate_limit(ip: str, max_attempts: int = 5, window_seconds: int = 60) -> bool:
    """Enforce per-IP rate limit. Returns True if request is allowed, False if rate-limited."""
    now = time.time()
    window_start = now - window_seconds
    attempts = _rate_limit_store[ip]
    # Prune old entries outside the sliding window
    _rate_limit_store[ip] = [t for t in attempts if t > window_start]
    if len(_rate_limit_store[ip]) >= max_attempts:
        return False
    _rate_limit_store[ip].append(now)
    return True

def get_client_ip(request: Request) -> str:
    """Extract client IP, only trusting X-Forwarded-For from Fly.io internal proxies."""
    client_host = request.client.host if request.client else "unknown"
    trusted_prefixes = ("10.", "172.16.", "192.168.", "fd00:", "::1")
    if any(client_host.startswith(p) for p in trusted_prefixes):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return client_host

# ── FastAPI Application ──────────────────────────────────────────────

app = FastAPI(
    title="Mirror.ng API",
    description="Financial mirror for Nigerian bank alerts with ML insights",
    version="2.0.0"
)

# ── CORS ─────────────────────────────────────────────────────────────

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Session Middleware (OAuth state storage) ─────────────────────────

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET_KEY"],
    max_age=3600,
    same_site="lax",
    https_only=HTTPS_ONLY
)

# ── OAuth (Google / Gmail API) ───────────────────────────────────────

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile https://www.googleapis.com/auth/gmail.readonly',
        'redirect_uri': os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8000/api/auth/google/callback'),
        'code_challenge_method': 'S256'
    }
)

# ============ EMAIL FETCHER CLASSES ============

class EmailFetcher:
    """Unified email fetcher for Yahoo IMAP, Gmail IMAP, and Gmail API"""

    def __init__(self, email_address: str, password: str = None, provider: str = 'yahoo',
                 access_token: str = None, refresh_token: str = None):
        self.email_address = email_address
        self.password = password
        self.provider = provider
        self.access_token = access_token
        self.refresh_token = refresh_token

    def connect_imap(self):
        """Open an IMAP SSL connection to Yahoo or Gmail.

        Returns:
            An authenticated imaplib.IMAP4_SSL instance with INBOX selected.

        Raises:
            ValueError: If credentials are invalid or the connection times out.
        """
        if self.provider == 'yahoo':
            server = "imap.mail.yahoo.com"
            port = 993
        else:
            server = "imap.gmail.com"
            port = 993

        try:
            import socket
            socket.setdefaulttimeout(60)
            mail = imaplib.IMAP4_SSL(server, port)
            mail.login(self.email_address, self.password)
            mail.select("INBOX")
            logger.info(f"Connected to {self.provider.upper()} IMAP for sync")
            return mail
        except TimeoutError:
            raise ValueError(f"{self.provider.upper()} IMAP timed out.")
        except imaplib.IMAP4.error:
            raise ValueError(f"Invalid {self.provider.upper()} credentials.")
        except Exception:
            raise

    def fetch_via_imap(self, sender_patterns: List[str], limit: int = 100,
                       since_date: Optional[str] = None,
                       until_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch bank alert emails via IMAP per-sender-pattern.

        Searches each sender pattern individually so only bank emails are
        returned — never pulls the full inbox. Results are sorted oldest-first
        so balance progression is correct.
        """
        mail = self.connect_imap()
        try:
            # Build date range strings once
            since_imap = None
            until_imap = None
            if since_date:
                since_imap = datetime.strptime(since_date, "%Y-%m-%d").strftime("%d-%b-%Y")
            if until_date:
                d_until = datetime.strptime(until_date, "%Y-%m-%d") + timedelta(days=1)
                until_imap = d_until.strftime("%d-%b-%Y")

            # Search per sender — ask Yahoo/Gmail for only bank emails
            all_message_ids = []
            seen = set()

            for pattern in sender_patterns:
                # Strip leading @ for FROM search (Yahoo needs bare domain or full address)
                search_pattern = pattern.lstrip("@")
                criteria_parts = [f'FROM "{search_pattern}"']
                if since_imap:
                    criteria_parts.append(f'SINCE {since_imap}')
                if until_imap:
                    criteria_parts.append(f'BEFORE {until_imap}')
                criteria = " ".join(criteria_parts)

                try:
                    status, messages = mail.search(None, criteria)
                    if status == "OK" and messages[0]:
                        for mid in messages[0].split():
                            if mid not in seen:
                                seen.add(mid)
                                all_message_ids.append(mid)
                except Exception as e:
                    logger.debug(f"Search failed for pattern '{pattern}': {e}")
                    continue

            # SECURITY: only search results for bank sender patterns — never raw inbox
            logger.info(f"Found {len(all_message_ids)} bank alert emails across all senders")

            if not all_message_ids:
                return []

            bank_emails = []
            for msg_id in reversed(all_message_ids):
                try:
                    status, msg_data = mail.fetch(msg_id, "(RFC822)")
                    if status != "OK":
                        continue
                    msg = email.message_from_bytes(msg_data[0][1], policy=default)
                    bank_emails.append({
                        "subject": msg.get("Subject", ""),
                        "from": msg.get("From", ""),
                        "raw": self._get_email_body(msg),
                        "date": msg.get("Date", ""),
                        "message_id": msg.get("Message-ID", "")
                    })
                except Exception as e:
                    logger.debug(f"Skipping email {msg_id}: {e}")
                    continue

            logger.info(f"Fetched {len(bank_emails)} bank alert emails")
            return bank_emails

        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def fetch_via_gmail_api(self, sender_patterns: List[str], limit: int = 100,
                            since_date: Optional[str] = None,
                            until_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch bank alert emails via the Gmail API using OAuth2 access tokens.

        Builds an OR query from all sender patterns so a single API call
        returns only bank-relevant messages. Handles token refresh if expired.
        """
        try:
            creds = Credentials(
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv('GOOGLE_CLIENT_ID'),
                client_secret=os.getenv('GOOGLE_CLIENT_SECRET')
            )

            if creds.expired:
                creds.refresh(GoogleRequest())

            service = build('gmail', 'v1', credentials=creds)

            # Build a combined OR query from all bank sender patterns
            bank_queries = [f'from:({pattern})' for pattern in sender_patterns]
            bank_domains = ' OR '.join(bank_queries)
            query = f'({bank_domains})'

            if since_date:
                query += f' after:{since_date.replace("-", "/")}'

            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=limit
            ).execute()

            bank_emails = []
            for msg in results.get('messages', []):
                msg_data = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()

                headers = {h['name'].lower(): h['value'] for h in msg_data['payload'].get('headers', [])}
                body = self._extract_gmail_body(msg_data['payload'])

                bank_emails.append({
                    "subject": headers.get('subject', ''),
                    "from": headers.get('from', ''),
                    "raw": body,
                    "date": headers.get('date', ''),
                    "message_id": msg['id']
                })

            logger.info(f"Gmail API: Found {len(bank_emails)} bank alert emails")
            return bank_emails

        except Exception as e:
            logger.error(f"Gmail API error: {e}", exc_info=True)
            raise ValueError(f"Gmail API error: {e}")

    def fetch_alerts(self, sender_patterns: List[str], limit: int = 100,
                     since_date: Optional[str] = None,
                     until_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Dispatch to the correct fetch method based on the provider.

        Gmail OAuth users hit the Gmail API; Yahoo / Gmail App Password users use IMAP.
        """
        if self.provider == 'gmail_oauth' and self.access_token:
            return self.fetch_via_gmail_api(sender_patterns, limit, since_date, until_date)
        else:
            return self.fetch_via_imap(sender_patterns, limit, since_date, until_date)

    def _get_email_body(self, msg) -> str:
        """Extract and decode the plain-text body from an IMAP email message.

        Tries text/plain first, falls back to text/html with HTML stripped.
        """
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

    def _extract_gmail_body(self, payload: dict) -> str:
        """Recursively extract the plain-text body from a Gmail API message payload."""
        if 'parts' in payload:
            for part in payload['parts']:
                body = self._extract_gmail_body(part)
                if body:
                    return body
            return ""

        if payload.get('mimeType') == 'text/plain':
            data = payload.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        return ""

    def _decode_and_clean(self, part, is_html: bool = False) -> str:
        """Decode email part payload, handling quoted-printable, charset, and HTML stripping."""
        try:
            payload = part.get_payload(decode=True)
            if not payload:
                payload = part.get_payload()
                if isinstance(payload, list):
                    payload = payload[0] if payload else ""
            charset = part.get_content_charset() or 'utf-8'
            text = payload.decode(charset, errors='ignore') if isinstance(payload, bytes) else str(payload)
            if '=3D' in text or '=20' in text:
                try:
                    text = quopri.decodestring(text.encode('utf-8')).decode('utf-8', errors='ignore')
                except Exception:
                    pass
            if is_html:
                text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', text)
                html_entities = {'&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'"}
                for entity, char in html_entities.items():
                    text = text.replace(entity, char)
            return re.sub(r'\s+', ' ', text).strip()
        except Exception:
            return ""


# ============ TIMEOUT MIDDLEWARE ============

class TimeoutMiddleware(BaseHTTPMiddleware):
    """Abort requests that take longer than 300 seconds (5 minutes).

    Prevents long-lived connections from consuming workers indefinitely,
    particularly during email sync or LLM agent calls.
    """
    async def dispatch(self, request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=300.0)
        except asyncio.TimeoutError:
            return JSONResponse(
                {"detail": "Request timed out — Please try again"},
                status_code=504
            )

app.add_middleware(TimeoutMiddleware)


# ============ SECURITY HEADERS MIDDLEWARE ============

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply standard security headers to every response.

    Includes HSTS, XSS protection, CSP (env-configurable), and referrer policy.
    CSP default allows dev tooling; set CSP_POLICY env var for production.
    """
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        csp_policy = os.getenv("CSP_POLICY", "").strip()
        if csp_policy:
            response.headers["Content-Security-Policy"] = csp_policy
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' https://*.openrouter.ai; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Protect mutating endpoints against cross-site request forgery.

    Uses a double-submit cookie pattern: a csrf_token cookie is set on
    GET responses, and all POST/PUT/DELETE/PATCH requests must echo
    the same value in the X-CSRF-Token header.  Auth endpoints are
    exempt because the user does not yet have a session/CSRF token.
    """
    async def dispatch(self, request, call_next):
        # Skip CSRF for safe methods
        if request.method in ("GET", "HEAD", "OPTIONS"):
            response = await call_next(request)
            if not request.cookies.get("csrf_token"):
                csrf = secrets.token_urlsafe(32)
                response.set_cookie(
                    key="csrf_token", value=csrf, httponly=False,
                    secure=COOKIE_SECURE, samesite="lax", max_age=3600
                )
            return response

        # Skip CSRF for auth and onboarding endpoints
        auth_paths = [
            "/api/auth/email-login",
            "/api/auth/google/login",
            "/api/auth/google/callback",
            "/api/auth/logout",
            "/api/onboarding-gaps",
            "/api/sync",
            "/api/sync/background"
        ]
        if any(request.url.path.startswith(path) for path in auth_paths):
            return await call_next(request)

        # Require CSRF token for all other state-changing requests
        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            return JSONResponse({"detail": "CSRF token mismatch"}, status_code=403)

        return await call_next(request)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)


# ============ APP EVENTS ============

@app.on_event("startup")
async def startup_event():
    """Initialise database schema, ML classifier, and background tasks on application start.

    Raises RuntimeError if required secrets are unset or use insecure defaults.
    """
    # SECURITY: validate required secrets before accepting any traffic
    required_secrets = ["SECRET_KEY", "SESSION_SECRET_KEY", "EMAIL_ENCRYPTION_KEY"]
    for s in required_secrets:
        val = os.getenv(s, "")
        if val.strip() in ("", "change-this-in-production"):
            raise RuntimeError(f"{s} is not set or is using an insecure default. "
                               f"Generate a random value with: python -c \"import secrets; print(secrets.token_hex(32))\"")

    init_db()
    logger.info("Database initialized")
    
    # Ensure exact_match column exists in user_aliases (safe migration)
    conn = get_db()
    try:
        conn.execute('ALTER TABLE user_aliases ADD COLUMN exact_match INTEGER DEFAULT 0')
        conn.commit()
        logger.info("Added exact_match column to user_aliases")
    except Exception:
        pass  # Column already exists — ignore
    finally:
        conn.close()
    
    try:
        train_classifier()
        logger.info("ML Classifier trained and ready")
    except Exception as e:
        logger.error(f"ML training failed on startup: {e}")

    # Background task: clean up expired sync jobs every 5 minutes
    async def cleanup_sync_jobs():
        while True:
            await asyncio.sleep(300)
            now = time.time()
            with _sync_jobs_lock:
                expired = [jid for jid, j in _sync_jobs.items()
                          if j["status"] in ("completed", "failed") and now - j["updated_at"] > 300]
                for jid in expired:
                    del _sync_jobs[jid]
                if expired:
                    logger.info(f"Cleaned up {len(expired)} expired sync jobs")

    asyncio.create_task(cleanup_sync_jobs())

@app.get("/health")
async def health_check():
    """Simple health-check endpoint for load balancers and monitoring."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ============ AUTHENTICATION ROUTES ============

# ── Google OAuth ─────────────────────────────────────────────────────

@app.get("/api/auth/google/login")
async def google_login(request: Request):
    """Initiate Google OAuth2 login flow. Redirects user to Google's consent screen."""
    redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8000/api/auth/google/callback')
    # SECURITY: generate anti-CSRF state token and store in session
    state = secrets.token_hex(32)
    request.session['oauth_state'] = state
    return await oauth.google.authorize_redirect(request, redirect_uri, state=state)

@app.get("/api/auth/google/callback")
async def google_auth_callback(request: Request):
    """Handle the OAuth2 callback from Google after user consents.

    Verifies the state parameter (CSRF protection), exchanges the auth code
    for tokens, creates/updates the user record, and sets a httpOnly JWT cookie.
    """
    try:
        # SECURITY: verify OAuth state to prevent CSRF
        expected_state = request.session.pop('oauth_state', None)
        actual_state = request.query_params.get('state')
        if not expected_state or not actual_state or expected_state != actual_state:
            logger.error("OAuth state mismatch — possible CSRF attack")
            return JSONResponse({"success": False, "error": "Authentication failed"}, status_code=400)

        token = await oauth.google.authorize_access_token(request)
        # Try token first (openid scope includes it), fall back to API call
        userinfo = token.get('userinfo')
        if not userinfo:
            resp = await oauth.google.get(
                'https://www.googleapis.com/oauth2/v1/userinfo', token=token
            )
            userinfo = resp if isinstance(resp, dict) else await resp.json()

        email_addr = userinfo.get('email')
        name = userinfo.get('name')

        if not email_addr:
            raise ValueError("No email received from Google")

        conn = get_db()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                auth_provider TEXT DEFAULT 'yahoo',
                access_token TEXT,
                refresh_token TEXT,
                email_password_enc TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        cursor = conn.execute('SELECT * FROM users WHERE email = ?', (email_addr,))
        user = cursor.fetchone()

        # SECURITY: encrypt OAuth tokens before storing
        if not user:
            enc_access_token = encrypt_email_password(token.get('access_token')) if token.get('access_token') else None
            enc_refresh_token = encrypt_email_password(token.get('refresh_token')) if token.get('refresh_token') else None
            cursor = conn.execute('''
                INSERT INTO users (email, name, auth_provider, access_token, refresh_token)
                VALUES (?, ?, ?, ?, ?) RETURNING id
            ''', (email_addr, name, 'gmail_oauth', enc_access_token, enc_refresh_token))
            user_id = cursor.fetchone()['id']
        else:
            user_id = user['id']
            enc_access_token = encrypt_email_password(token.get('access_token')) if token.get('access_token') else None
            enc_refresh_token = encrypt_email_password(token.get('refresh_token')) if token.get('refresh_token') else None
            conn.execute('''
                UPDATE users SET access_token = ?, refresh_token = ?, auth_provider = ? WHERE id = ?
            ''', (enc_access_token, enc_refresh_token, 'gmail_oauth', user_id))

        conn.commit()
        conn.close()

        session_token = create_access_token({"user_id": str(user_id), "email": email_addr})
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        response = RedirectResponse(url=f"{frontend_url}/auth/callback?logged_in=1")
        # SECURITY: httpOnly + Secure + SameSite=Lax JWT cookie
        response.set_cookie(
            key="mirror_token",
            value=session_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            max_age=604800,
            path="/"
        )
        return response

    except Exception:
        logger.error(f"Google auth error")
        return JSONResponse({"success": False, "error": "Authentication failed"}, status_code=400)


# ── Email / IMAP Login ───────────────────────────────────────────────

@app.post("/api/auth/email-login")
async def email_login(request: Request):
    """Authenticate via IMAP credentials (Yahoo / Gmail App Password).

    Tests credentials against the IMAP server, then stores the encrypted
    password for background sync use. Returns a httpOnly JWT cookie.
    """
    # SECURITY: rate-limit to 5 attempts per 60 s per IP
    client_ip = get_client_ip(request)
    if not check_rate_limit(client_ip):
        logger.warning(f"Rate limit hit for {client_ip}")
        return JSONResponse({
            "success": False,
            "error": "Too many login attempts. Try again later."
        }, status_code=429)

    data = await request.json()
    email_addr = data.get('email')
    password = data.get('password')
    provider = data.get('provider', 'yahoo')

    if provider == 'gmail_app':
        provider = 'gmail'

    try:
        # Verify credentials against the IMAP server before storing anything
        server = "imap.mail.yahoo.com" if provider == 'yahoo' else "imap.gmail.com"
        import socket
        socket.setdefaulttimeout(15)
        mail = imaplib.IMAP4_SSL(server, 993)
        mail.login(email_addr, password)
        mail.logout()

        conn = get_db()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                auth_provider TEXT DEFAULT 'yahoo',
                access_token TEXT,
                refresh_token TEXT,
                email_password_enc TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

        try:
            conn.execute('ALTER TABLE users ADD COLUMN email_password_enc TEXT')
            conn.commit()
        except Exception:
            pass

        cursor = conn.execute('SELECT * FROM users WHERE email = ?', (email_addr,))
        user = cursor.fetchone()

        # SECURITY: encrypt password with Fernet before storing
        if not user:
            cursor = conn.execute('''
                INSERT INTO users (email, name, auth_provider, email_password_enc)
                VALUES (?, ?, ?, ?) RETURNING id
            ''', (email_addr, email_addr.split('@')[0] if '@' in email_addr else email_addr, provider, encrypt_email_password(password)))
            user_id = cursor.fetchone()['id']
        else:
            user_id = user['id']
            conn.execute('UPDATE users SET email_password_enc = ? WHERE id = ?',
                         (encrypt_email_password(password), user_id))

        conn.commit()
        conn.close()

        token = create_access_token({"user_id": str(user_id), "email": email_addr})
        # SECURITY: httpOnly cookie — token is not accessible to JS
        response = JSONResponse({
            "success": True,
            "user": {"user_id": user_id, "email": email_addr, "provider": provider}
        })
        response.set_cookie(
            key="mirror_token",
            value=token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            max_age=604800,
            path="/"
        )
        return response

    except Exception:
        # PII-safe: only log first 3 chars and domain of the email
        logger.error(f"Email login failed for {email_addr[:3]}***@{email_addr.split('@')[1] if '@' in email_addr else 'unknown'}")
        return JSONResponse({
            "success": False,
            "error": "Login failed. Check your credentials and try again."
        }, status_code=401)


@app.get("/api/auth/me")
async def auth_me(request: Request):
    """Return the authenticated user's ID from the JWT cookie."""
    token_user_id = await get_current_user_id(request)
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": token_user_id}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    """Blacklist the JWT and clear the cookie to log the user out."""
    token = request.cookies.get("mirror_token")
    if token:
        payload = decode_access_token(token)
        if payload:
            jti, exp = payload.get("jti"), payload.get("exp")
            if jti and exp:
                conn = get_db()
                conn.execute(
                    'INSERT OR IGNORE INTO token_blacklist (jti, expires_at) VALUES (?, datetime(?, "unixepoch"))',
                    (jti, exp)
                )
                conn.commit()
                conn.close()
    response.delete_cookie("mirror_token", path="/")
    return {"success": True, "message": "Logged out"}


# ============ TRANSACTION ROUTES ============

# ── Alias Pattern Matching ──────────────────────────────────────────

def _matches_composite_pattern(tx: dict, pattern: str) -> bool:
    """Check if a transaction matches an alias pattern.

    Supports three formats in priority order:
      1. ``tx:{id}`` — 100% unique primary-key match (no collisions)
      2. ``YYYY-MM-DD|narration`` — date + exact-narration (legacy)
      3. Plain substring on narration (fallback)
    """
    if not pattern:
        return False
    
    # Format 1: "tx:{id}" — unambiguous primary-key reference
    if pattern.startswith('tx:'):
        pattern_id = pattern[3:].strip()
        tx_id = str(tx.get('id', '')).strip()
        return tx_id == pattern_id
    
    # Format 2: "YYYY-MM-DD|narration" — legacy date-pipe format
    if '|' in pattern:
        parts = pattern.split('|', 1)
        if len(parts) == 2:
            pattern_date, pattern_narration = parts[0].strip(), parts[1].strip()
            tx_timestamp = tx.get('timestamp', '') or ''
            tx_date = tx_timestamp.split('T')[0] if 'T' in tx_timestamp else tx_timestamp[:10]
            tx_narration = (tx.get('narration') or '').strip()
            return tx_date == pattern_date and tx_narration == pattern_narration
    
    # Format 3: simple substring match on narration (fallback)
    tx_narration = (tx.get('narration') or '').lower().strip()
    return pattern.lower().strip() in tx_narration


# ============ TRANSACTIONS ENDPOINT ============

@app.get("/api/transactions/{user_id}")
async def get_transactions(user_id: str, req: Request, limit: int = 50, offset: int = 0, bank: Optional[str] = None):
    """Return paginated transactions for a user, with alias enrichment.

    Each transaction is checked against the user's alias rules. Matched
    transactions get ``aliased=True``, ``alias_name``, and ``alias_category``.
    """
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        # Fetch user aliases for inline matching
        alias_cursor = conn.execute(
            'SELECT recipient_pattern, display_name, category, exact_match FROM user_aliases WHERE user_id = ?',
            (user_id,)
        )
        aliases = [dict(row) for row in alias_cursor.fetchall()]
        
        if bank:
            cursor = conn.execute('''
                SELECT * FROM transactions WHERE user_id = ? AND bank = ?
                ORDER BY timestamp DESC LIMIT ? OFFSET ?
            ''', (user_id, bank, limit, offset))
        else:
            cursor = conn.execute('''
                SELECT * FROM transactions WHERE user_id = ?
                ORDER BY timestamp DESC LIMIT ? OFFSET ?
            ''', (user_id, limit, offset))
        
        transactions = []
        aliased_count = 0
        
        for row in cursor.fetchall():
            tx = dict(row)
            # Apply alias matching to decorate the transaction
            matched_alias = None
            for alias in aliases:
                pattern = alias.get('recipient_pattern') or ''
                exact_match = bool(alias.get('exact_match', 0))
                
                if exact_match:
                    if _matches_composite_pattern(tx, pattern):
                        matched_alias = alias
                        break
                else:
                    tx_narration = (tx.get('original_narration') or tx.get('narration') or '').lower()
                    if pattern and pattern.lower() in tx_narration:
                        matched_alias = alias
                        break
            
            if matched_alias:
                tx['aliased'] = True
                tx['alias_name'] = matched_alias.get('display_name')
                tx['alias_category'] = matched_alias.get('category', 'General')
                aliased_count += 1
            else:
                tx['aliased'] = False
            
            transactions.append(tx)
        
        return JSONResponse({
            "success": True,
            "transactions": transactions,
            "count": len(transactions),
            "has_more": len(transactions) == limit
        })
    except Exception as e:
        logger.error(f"Error fetching transactions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch transactions")
    finally:
        conn.close()


# ── Core Sync Logic (blocking, reusable) ──────────────────────────────

# ── Core Sync Logic (blocking, reusable) ──────────────────────────────

def _sync_transactions_blocking(
    request: SyncRequest,
    user_id: str,
    conn,
    progress_callback: Optional[Callable] = None
) -> dict:
    """Execute the full email-to-database sync pipeline.

    Synchronous by design — safe to call from either a request handler
    or a background daemon thread. The pipeline follows these phases:

    1. User lookup + credential decryption
    2. IMAP / Gmail API fetch (filtered by bank sender patterns)
    3. Per-email subject filter → bank-parser → category ML
    4. Deduplication and INSERT into ``transactions``
    5. Opening-balance anchoring + onboarding gap detection
    6. ``last_sync_at`` timestamp update

    Args:
        request: The validated SyncRequest containing date range and options.
        user_id: Authenticated user ID (int or string).
        conn: Open SQLite connection (``check_same_thread=False``).
        progress_callback: Optional callable for background-job progress reporting.

    Returns:
        A dict with ``success``, the list of parsed transactions, gap info, and metadata.
    """
    # ── Phase 1: User lookup ─────────────────────────────────────────

    cursor = conn.execute('''
        SELECT email, auth_provider, access_token, refresh_token, email_password_enc, last_sync_at, name
        FROM users WHERE id = ?
    ''', (user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=400, detail="User not found.")

    email_addr = user['email']
    provider = user['auth_provider'] or 'yahoo'

    if progress_callback:
        progress_callback(5, 0, 0, "Authenticated...")

    # ── Phase 2: Incremental-sync date window ────────────────────────

    effective_since = request.since_date
    last_sync_at = user['last_sync_at']
    if not request.full_sync and not effective_since and last_sync_at:
        effective_since = last_sync_at.split('T')[0]
    if not effective_since:
        effective_since = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    if not email_addr:
        raise HTTPException(status_code=400, detail="Email not found. Please login again.")

    # ── Phase 2b: Check cloud-sync preference ────────────────────────

    pref_cursor = conn.execute('SELECT cloud_sync FROM user_prefs WHERE user_id = ?', (user_id,))
    pref_row = pref_cursor.fetchone()
    cloud_sync = bool(pref_row['cloud_sync']) if pref_row else True

    # ── Phase 3: Build the appropriate email fetcher ─────────────────

    if provider == 'gmail_oauth':
        # SECURITY: decrypt OAuth tokens that were stored encrypted
        raw_access = user['access_token']
        if not raw_access:
            raise HTTPException(status_code=400, detail="Google OAuth session expired. Please login again.")
        access_token = decrypt_email_password(raw_access) if raw_access and raw_access.startswith('gAAAAA') else raw_access
        refresh_token = decrypt_email_password(user['refresh_token']) if user.get('refresh_token') and user['refresh_token'].startswith('gAAAAA') else user.get('refresh_token')
        fetcher = EmailFetcher(
            email_address=email_addr,
            password=None,
            provider=provider,
            access_token=access_token,
            refresh_token=refresh_token
        )
    else:
        enc_pw = user['email_password_enc']
        if not enc_pw:
            raise HTTPException(status_code=400, detail="Password not stored. Please login again.")
        password = decrypt_email_password(enc_pw)
        if not password:
            raise HTTPException(
                status_code=401,
                detail="Email credentials expired. Please re-authenticate your email account."
            )
        fetcher = EmailFetcher(
            email_address=email_addr,
            password=password,
            provider=provider,
            access_token=None,
            refresh_token=None
        )

    # ── Phase 4: Fetch bank alert emails ─────────────────────────────

    sender_patterns = [
        "e-business@sterling.ng",
        "no-reply@alat.ng",
        "no-reply@11054915.brevosend.com",
        "no-reply@opay-nigeria.com",
        "gtbank.com",
        "accessbankplc.com",
        "firstbanknigeria.com",
        "kuda.com",
        "moniepoint.com",
        "palmspay.com",
        "StanbicIBTC-E-Alert@stanbicibtc.com",
        "alerts.nigeria@sc.com",
        "no-reply@moniepoint.com",
        "GeNS@gtbank.com",
    ]

    email_alerts = fetcher.fetch_alerts(
        sender_patterns=sender_patterns,
        since_date=effective_since,
        until_date=request.until_date
    )

    if progress_callback:
        progress_callback(30, 0, len(email_alerts), f"Fetched {len(email_alerts)} emails")

    # Sort oldest-first so balance progression is correct
    def safe_parse_date(x):
        try:
            return email_utils.parsedate_to_datetime(x.get('date', ''))
        except Exception:
            return datetime.min

    email_alerts.sort(key=safe_parse_date)

    # ── Phase 5: Parse emails into structured transactions ───────────

    balance_manager = BalanceManager(conn)
    new_transactions = []
    latest_timestamp = None
    stored = 0

    TRANSACTION_KEYWORDS = [
        "money out", "money in", "debit alert", "credit alert",
        "transaction", "ngn", "credited", "debited", "debit", "credit",
        "transfer successful", "transfer",
    ]

    BLOCKED_SUBJECTS = [
        "verification code", "otp", "home hacks", "newsletter",
        "you logged in", "login", "logged into", "promo", "offer",
        "update", "welcome", "verify your"
    ]

    total_emails = len(email_alerts)
    for idx, alert in enumerate(email_alerts):
        subject = alert.get("subject", "").lower()

        if progress_callback and idx % 5 == 0:
            pct = 40 + int((idx / total_emails) * 50) if total_emails > 0 else 40
            progress_callback(pct, idx, total_emails, f"Parsing email {idx+1} of {total_emails}...")

        # Skip non-transaction emails (OTP, newsletters, etc.)
        if any(b in subject for b in BLOCKED_SUBJECTS):
            continue

        if not any(kw in subject for kw in TRANSACTION_KEYWORDS):
            continue

        try:
            parser = get_parser_for_sender(alert["from"])
            if not parser:
                continue

            parsed_tx = parser.parse(alert.get("subject", ""), alert["raw"])
            if not parsed_tx:
                continue

            # Normalise last-4 digits to guard against whitespace/padding
            normalized_last4 = str(parsed_tx.account_last4)[-4:] if parsed_tx.account_last4 else None

            # ML category prediction from raw narration
            parsed_tx.category = predict_category(parsed_tx.narration)

            # DEBUG: Log what was parsed
            logger.info(f"Parsed: {parsed_tx.bank} | Type: {parsed_tx.tx_type} | Narration: '{parsed_tx.narration}' | Amount: {parsed_tx.amount}")

            if parsed_tx.timestamp and (not latest_timestamp or parsed_tx.timestamp > latest_timestamp):
                latest_timestamp = parsed_tx.timestamp
            new_transactions.append(parsed_tx)
        except Exception as e:
            # Individual alert failures must never abort the entire batch
            logger.debug(f"Error processing alert: {e}")

    # ── Phase 6: Persist to database (ALWAYS store, regardless of cloud_sync) ──

    for parsed_tx in new_transactions:
        normalized_last4 = str(parsed_tx.account_last4)[-4:] if parsed_tx.account_last4 else None
        # SECURITY: composite-key lookup prevents cross-user duplicates
        cursor = conn.execute('''
            SELECT id FROM transactions
            WHERE user_id = ? AND bank = ? AND amount = ? AND timestamp = ?
            AND (narration = ? OR original_narration = ?)
        ''', (user_id, parsed_tx.bank, parsed_tx.amount,
              parsed_tx.timestamp.isoformat() if parsed_tx.timestamp else "",
              parsed_tx.narration, parsed_tx.narration))
        if cursor.fetchone():
            continue

        try:
            original_narration = parsed_tx.narration
            smart_narration = clean_narration(parsed_tx.narration, parsed_tx.bank)

            cursor = conn.execute('''
                INSERT INTO transactions
                (user_id, bank, tx_type, amount, narration, original_narration, cleaned_narration, account_last4, timestamp, category, balance_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            ''', (
                user_id, parsed_tx.bank, parsed_tx.tx_type,
                parsed_tx.amount, smart_narration, original_narration, smart_narration, normalized_last4,
                parsed_tx.timestamp.isoformat() if parsed_tx.timestamp else "",
                parsed_tx.category, 0.0
            ))
            tx_id = cursor.fetchone()['id']
            new_balance = balance_manager.update_balance_from_transaction(user_id, parsed_tx)
            if new_balance is not None:
                conn.execute('UPDATE transactions SET balance_after = ? WHERE id = ?', (new_balance, tx_id))
            stored += 1
        except Exception as e:
            # Per-row failures must not break the entire batch
            logger.debug(f"Error storing: {e}")

    conn.commit()
    logger.info(f"Sync: stored {stored} new transactions")

    if progress_callback:
        progress_callback(95, stored, len(new_transactions), f"Stored {stored} new transactions")

    # ── Process opening balances ─────────────────────────────────────

    if request.opening_balances:
        active_accounts = set()
        for tx in new_transactions:
            if tx.bank and tx.account_last4:
                active_accounts.add((tx.bank, str(tx.account_last4)[-4:]))

        for ob in request.opening_balances:
            is_active = (ob.bank, ob.account_last4) in active_accounts
            logger.debug(f"Opening balance: {ob.bank}/**{ob.account_last4[-2:]} processed")
            conn.execute('''
                DELETE FROM account_balances
                WHERE user_id = ? AND bank = ? AND account_last4 = ?
            ''', (user_id, ob.bank, ob.account_last4))
            conn.execute('''
                INSERT INTO account_balances
                (user_id, bank, account_last4, balance, last_updated, is_anchor)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, ob.bank, ob.account_last4, ob.balance,
                  datetime.now().isoformat(), 1 if is_active else 0))
        conn.commit()

    # ── Gap detection (works on DB data now) ─────────────────────────

    cursor = conn.execute('''
        SELECT 
            bank,
            account_last4,
            MAX(CASE WHEN account_last4 IS NOT NULL AND account_last4 != '' AND account_last4 != '0000' THEN 1 ELSE 0 END) as has_account,
            MAX(CASE WHEN balance_after IS NOT NULL AND balance_after != 0 THEN 1 ELSE 0 END) as has_balance
        FROM transactions
        WHERE user_id = ?
        GROUP BY bank, account_last4
    ''', (user_id,))
    tx_accounts = [dict(r) for r in cursor.fetchall()]

    anchored = set()
    cursor = conn.execute('''
        SELECT DISTINCT bank, account_last4
        FROM account_balances
        WHERE user_id = ? AND is_anchor = 1
    ''', (user_id,))
    for r in cursor.fetchall():
        anchored.add((r['bank'], r['account_last4']))

    gaps, total_accounts = detect_onboarding_gaps(tx_accounts, anchored)

    # ── Phase 7: Update last_sync_at timestamp ───────────────────────

    if latest_timestamp:
        new_sync_date = latest_timestamp.isoformat()
    else:
        new_sync_date = datetime.now().isoformat()
    conn.execute('UPDATE users SET last_sync_at = ? WHERE id = ?', (new_sync_date, user_id))
    conn.commit()

    if progress_callback:
        progress_callback(100, 0, 0, "Sync complete")

    return {
        "success": True,
        "new_transactions": [tx.to_dict() for tx in new_transactions],
        "total_synced": len(new_transactions),
        "cloud_sync": cloud_sync,
        "incremental": not request.full_sync,
        "since_date_used": effective_since,
        "gaps": gaps,
        "total_accounts": total_accounts,
    }


# ── Sync Endpoint (thin async wrapper) ────────────────────────────────

@app.post("/api/sync")
async def sync_transactions(request: SyncRequest, req: Request):
    """Synchronous sync endpoint. Runs the blocking sync and returns results inline."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != request.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # SECURITY: rate-limit to 15 requests per minute per IP
    if not check_rate_limit(get_client_ip(req), max_attempts=15, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")
    conn = get_db()
    try:
        result = _sync_transactions_blocking(request, token_user_id, conn)
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail="Sync failed. Please try again.")
    finally:
        conn.close()


# ── Background Sync ──────────────────────────────────────────────────

class SyncBackgroundRequest(PydanticBase):
    """Request to start an async background sync job (returns job_id for polling)."""
    user_id: str
    since_date: Optional[str] = None
    until_date: Optional[str] = None
    full_sync: bool = False
    opening_balances: List[OpeningBalanceItem] = []


@app.post("/api/sync/background")
async def sync_background(request: SyncBackgroundRequest, req: Request):
    """Kick off a sync on a daemon thread and return a ``job_id`` for status polling.

    The caller polls ``GET /api/sync/status/{job_id}`` to track progress.
    """
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != request.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not check_rate_limit(get_client_ip(req), max_attempts=15, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")
    job_id = str(uuid.uuid4())
    now = time.time()

    sync_req = SyncRequest(
        user_id=request.user_id,
        since_date=request.since_date,
        until_date=request.until_date,
        full_sync=request.full_sync,
        opening_balances=request.opening_balances
    )

    # Initialise job state under lock to avoid races on first write
    job = {
        "status": "running",
        "progress": 0,
        "emails_processed": 0,
        "total_emails": 0,
        "message": "Starting...",
        "result": None,
        "user_id": request.user_id,
        "created_at": now,
        "updated_at": now,
    }

    with _sync_jobs_lock:
        _sync_jobs[job_id] = job

    def progress_callback(pct, processed, total, msg):
        """Inline updater called from _sync_transactions_blocking on the background thread."""
        with _sync_jobs_lock:
            j = _sync_jobs.get(job_id)
            if j:
                j["progress"] = pct
                j["emails_processed"] = processed
                j["total_emails"] = total
                j["message"] = msg
                j["updated_at"] = time.time()

    def run_sync():
        """Target for the daemon thread — opens its own DB connection."""
        conn = get_db()
        try:
            result = _sync_transactions_blocking(sync_req, token_user_id, conn, progress_callback)
            with _sync_jobs_lock:
                j = _sync_jobs.get(job_id)
                if j:
                    j["status"] = "completed"
                    j["result"] = result
                    j["updated_at"] = time.time()
        except HTTPException as e:
            with _sync_jobs_lock:
                j = _sync_jobs.get(job_id)
                if j:
                    j["status"] = "failed"
                    j["message"] = e.detail
                    j["updated_at"] = time.time()
        except Exception as e:
            with _sync_jobs_lock:
                j = _sync_jobs.get(job_id)
                if j:
                    j["status"] = "failed"
                    j["message"] = str(e)
                    j["updated_at"] = time.time()
        finally:
            conn.close()

    thread = threading.Thread(target=run_sync, daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "started"}


@app.get("/api/sync/status/{job_id}")
async def get_sync_status(job_id: str, req: Request):
    """Poll the progress and result of a background sync job by its ``job_id``."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    with _sync_jobs_lock:
        job = _sync_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # SECURITY: only the owning user may poll their own job
    if job.get("user_id") != token_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    resp = {
        "status": job["status"],
        "progress": job["progress"],
        "emails_processed": job["emails_processed"],
        "total_emails": job["total_emails"],
        "message": job["message"],
    }

    if job["status"] == "completed":
        resp["result"] = job["result"]

    return resp


# ============ AGENT / CHAT ROUTES ============

# ── In-Memory DB Helper ──────────────────────────────────────────────

def _make_local_db(transactions, user_id=None):
    """Create an in-memory SQLite DB from client-supplied local transactions for agent queries.

    Used when cloud sync is OFF — the agent queries an ephemeral mirror of the
    persistent schema without writing anything to disk.
    """
    mem = sqlite3.connect(':memory:')
    mem.row_factory = sqlite3.Row
    mem.execute('''
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, bank TEXT, tx_type TEXT, amount REAL,
            balance_after REAL, narration TEXT, original_narration TEXT, cleaned_narration TEXT, account_last4 TEXT,
            timestamp TEXT, category TEXT, alias_name TEXT
        )
    ''')
    # account_balances table mirrors the persistent schema for temporal queries
    mem.execute('''
        CREATE TABLE account_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL, bank TEXT NOT NULL,
            account_last4 TEXT NOT NULL, balance REAL NOT NULL,
            last_updated TEXT NOT NULL
        )
    ''')
    for tx in transactions:
        d = tx if isinstance(tx, dict) else (tx.model_dump() if hasattr(tx, 'model_dump') else {})
        tx_user_id = user_id or d.get('user_id')
        mem.execute('''
            INSERT INTO transactions (user_id, bank, tx_type, amount, balance_after, narration, original_narration, cleaned_narration, account_last4, timestamp, category, alias_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            tx_user_id, d.get('bank'), d.get('tx_type'), d.get('amount'),
            d.get('balance'), d.get('narration'), d.get('original_narration'), d.get('cleaned_narration'), d.get('account_last4'),
            d.get('timestamp'), d.get('category', 'other'), d.get('alias_name')
        ))
    mem.commit()
    return mem


# ── Agent Chat — v1 (run_agent) ──────────────────────────────────────

@app.post("/api/agent/chat")
async def agent_chat(request: AgentChatRequest, req: Request):
    """v1 agent chat endpoint — uses ``run_agent()`` for OpenRouter LLM Q&A."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != request.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not check_rate_limit(get_client_ip(req), max_attempts=15, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")
    is_local = bool(request.local_transactions)
    
    if is_local:
        mem_db = _make_local_db(request.local_transactions, request.user_id)
        try:
            temporal_context = get_agent_temporal_context(
                user_id=request.user_id,
                payload_since=request.since_date,
                payload_until=request.until_date,
                db_conn=mem_db
            )
            result = await run_agent(
                user_id=request.user_id,
                message=request.message,
                history=request.history,
                db_conn=mem_db,
                since_date=request.since_date,
                until_date=request.until_date,
                temporal_context=temporal_context
            )
            return JSONResponse({"success": True, **result})
        finally:
            mem_db.close()
    else:
        conn = get_db()
        try:
            temporal_context = get_agent_temporal_context(
                user_id=request.user_id,
                payload_since=request.since_date,
                payload_until=request.until_date,
                db_conn=conn
            )
            result = await run_agent(
                user_id=request.user_id,
                message=request.message,
                history=request.history,
                db_conn=conn,
                since_date=request.since_date,
                until_date=request.until_date,
                temporal_context=temporal_context
            )
            return JSONResponse({"success": True, **result})
        except Exception as e:
            logger.error(f"Agent error: {e}")
            raise HTTPException(status_code=500, detail="Agent failed")
        finally:
            conn.close()


# ── Agent Chat — v2 (intent-based) ───────────────────────────────────

@app.post("/api/agent/chat-v2")
async def agent_chat_v2(request: AgentChatRequest, req: Request):
    """v2 agent chat endpoint — uses ``run_intent_agent()`` for structured intent parsing.

    Faster than v1 for common queries (balance, spend-summary, category breakdown)
    because it uses deterministic SQL + pattern matching before falling back to the LLM.
    """
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != request.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if not check_rate_limit(get_client_ip(req), max_attempts=15, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")
    is_local = bool(request.local_transactions)
    
    if is_local:
        mem_db = _make_local_db(request.local_transactions, request.user_id)
        try:
            temporal_context = get_agent_temporal_context(
                user_id=request.user_id,
                payload_since=request.since_date,
                payload_until=request.until_date,
                db_conn=mem_db
            )
            result = run_intent_agent(
                user_id=request.user_id,
                message=request.message,
                history=request.history,
                db_conn=mem_db,
                since_date=request.since_date,
                until_date=request.until_date,
                temporal_context=temporal_context
            )
            return JSONResponse({"success": True, **result})
        finally:
            mem_db.close()
    else:
        conn = get_db()
        try:
            temporal_context = get_agent_temporal_context(
                user_id=request.user_id,
                payload_since=request.since_date,
                payload_until=request.until_date,
                db_conn=conn
            )
            result = run_intent_agent(
                user_id=request.user_id,
                message=request.message,
                history=request.history,
                db_conn=conn,
                since_date=request.since_date,
                until_date=request.until_date,
                temporal_context=temporal_context
            )
            return JSONResponse({"success": True, **result})
        except Exception as e:
            logger.error(f"Intent agent error: {e}")
            raise HTTPException(status_code=500, detail="Agent failed")
        finally:
            conn.close()


# ============ INSIGHTS & ANALYTICS ============

# ── Aggregated Insights ──────────────────────────────────────────────

@app.get("/api/insights/{user_id}")
async def get_insights(user_id: str, req: Request):
    """Aggregated analytics: anomalies, weekly forecast, top merchants, recurring payments.

    All four analytics are computed in-memory from the same transaction list
    to minimise DB round-trips.
    """
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        cursor = conn.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp ASC', (user_id,))
        transactions = [dict(row) for row in cursor.fetchall()]
        if not transactions:
            return {"success": True, "anomalies": [], "forecast": [], "merchants": [], "recurring": [], "message": "Insufficient data"}
        anomalies = [t for t in detect_anomalies(transactions) if t.get('is_anomaly')]
        forecast_data = weekly_spend_forecast(transactions)
        merchants = get_top_merchants(transactions)
        recurring = detect_recurring(transactions)
        return JSONResponse({
            'success': True,
            'anomalies': anomalies,
            'forecast': forecast_data,
            'merchants': merchants,
            'recurring': recurring,
            'stats': {
                'total_anomalies': len(anomalies),
                'total_analyzed': len(transactions),
                'total_merchants': len(merchants),
                'total_recurring': len(recurring),
            }
        })
    finally:
        conn.close()


@app.get("/api/insights/merchants/{user_id}")
async def get_merchant_insights(user_id: str, req: Request):
    """Top merchants breakdown (up to 50)."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        cursor = conn.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp ASC', (user_id,))
        transactions = [dict(row) for row in cursor.fetchall()]
        merchants = get_top_merchants(transactions, min_count=1, limit=50)
        return {"success": True, "merchants": merchants, "total": len(merchants)}
    finally:
        conn.close()


@app.get("/api/insights/recurring/{user_id}")
async def get_recurring_payments(user_id: str, req: Request):
    """Detect recurring/subscription payments from transaction history."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        cursor = conn.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp ASC', (user_id,))
        transactions = [dict(row) for row in cursor.fetchall()]
        recurring = detect_recurring(transactions)
        return {"success": True, "recurring": recurring, "total": len(recurring)}
    finally:
        conn.close()


# ============ BALANCES & ONBOARDING ============

# ============ BALANCES ============

@app.get("/api/balances/{user_id}")
async def get_balances(user_id: str, req: Request):
    """Return current balances per account, enriched with parser metadata.

    Enriches each balance with:
    - ``is_anchor``: whether it was manually set or auto-tracked
    - ``provides_balance``: whether the bank includes balance in email alerts
    """
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    balance_manager = BalanceManager(conn)
    try:
        balances = balance_manager.get_all_current_balances(user_id)

        from .parsers import PARSER_CLASSES
        BANK_PROVIDES_BALANCE = {}
        for ParserClass in PARSER_CLASSES:
            parser = ParserClass()
            provides = getattr(parser, 'PROVIDES_BALANCE', False)
            BANK_PROVIDES_BALANCE[parser.BANK_NAME] = provides

        for b in balances:
            b['is_anchor'] = bool(b.get('is_anchor', False))
            b['provides_balance'] = BANK_PROVIDES_BALANCE.get(b['bank'], False)
            # SECURITY: default to 0 to avoid exposing None in API responses
            b['balance'] = b.get('balance', 0) or 0

        return {"success": True, "balances": balances}
    finally:
        conn.close()


@app.post("/api/set-initial-balances")
async def set_initial_balances(request: InitialBalanceRequest, req: Request):
    """Bulk-set initial (anchor) balances for multiple accounts during onboarding."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != request.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    balance_manager = BalanceManager(conn)
    try:
        for account in request.balances:
            # Handle both Pydantic models and raw dicts
            if isinstance(account, dict):
                bank = account.get('bank')
                last4 = account.get('account_last4')
                balance = account.get('balance')
            else:
                bank = account.bank
                last4 = account.account_last4
                balance = account.balance

            if not bank or balance is None:
                continue

            norm_last4 = str(last4)[-4:]
            balance_manager.set_initial_balance(
                user_id=request.user_id,
                bank=bank,
                account_last4=norm_last4,
                balance=float(balance)
            )
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error setting initial balances: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.post("/api/manual-adjust-balance")
async def manual_adjust_balance(request: ManualAdjustRequest, req: Request):
    """Single-account balance override (manual correction on the settings page)."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != request.user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    balance_manager = BalanceManager(conn)
    try:
        norm_last4 = str(request.account_last4)[-4:]
        balance_manager.set_initial_balance(
            user_id=request.user_id,
            bank=request.bank,
            account_last4=norm_last4,
            balance=request.new_balance
        )
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


# ============ DELETE BALANCE ============

class DeleteBalanceRequest(PydanticBase):
    bank: str
    account_last4: str

@app.delete("/api/balances/{user_id}")
async def delete_balance(user_id: str, request: DeleteBalanceRequest, req: Request):
    """Remove a stored balance record — used when unlinking an account on the frontend."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        conn.execute(
            'DELETE FROM account_balances WHERE user_id = ? AND bank = ? AND account_last4 = ?',
            (user_id, request.bank, request.account_last4)
        )
        conn.commit()
        return JSONResponse({"success": True})
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete balance")
    finally:
        conn.close()


# ============ ALIAS ENDPOINTS ============
# Merchant aliases let users define display-name overrides that replace
# raw bank narration text with a friendly merchant name in the UI.

@app.get("/api/aliases/{user_id}")
async def get_aliases(user_id: str, req: Request):
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        cursor = conn.execute(
            'SELECT * FROM user_aliases WHERE user_id = ? ORDER BY created_at DESC',
            (user_id,)
        )
        aliases = []
        for row in cursor.fetchall():
            alias_dict = dict(row)
            # Convert exact_match from SQLite integer to boolean
            alias_dict['exact_match'] = bool(alias_dict.get('exact_match', 0))
            aliases.append(alias_dict)
        return JSONResponse({"success": True, "aliases": aliases})
    finally:
        conn.close()

@app.post("/api/aliases/{user_id}")
async def save_alias(user_id: str, payload: AliasRequest, req: Request = None):
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        logger.debug(f"Saving alias for user {user_id}")
        exact_match = 1 if payload.exact_match else 0

        cursor = conn.execute('''
            SELECT id FROM user_aliases 
            WHERE user_id = ? AND recipient_pattern = ?
        ''', (user_id, payload.recipient_pattern))
        existing = cursor.fetchone()

        if existing:
            conn.execute('''
                UPDATE user_aliases 
                SET display_name = ?, category = ?, exact_match = ?
                WHERE id = ?
            ''', (payload.display_name, payload.category, exact_match, existing['id']))
            alias_id = existing['id']
        else:
            cursor = conn.execute('''
                INSERT INTO user_aliases (user_id, recipient_pattern, display_name, category, exact_match)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, payload.recipient_pattern, payload.display_name, payload.category, exact_match))
            alias_id = cursor.lastrowid

        conn.commit()
        return JSONResponse({"success": True, "alias_id": alias_id})
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving alias: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save alias")
    finally:
        conn.close()

@app.post("/api/transactions/bulk-execute/{preview_id}")
async def bulk_execute(preview_id: str, req: Request):
    token_user_id = await get_current_user_id(req)
    if not token_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if preview_id not in _pending_bulk_updates:
        raise HTTPException(status_code=404, detail="Preview not found or expired")

    data = _pending_bulk_updates[preview_id]

    if data["user_id"] != token_user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    conn = get_db()
    try:
        transaction_ids = data["transaction_ids"]
        new_narration = data["new_narration"]
        new_category = data["new_category"]
        query_pattern = data.get("query", "")

        updated_count = len(transaction_ids)

        if query_pattern and updated_count > 0:
            cursor = conn.execute(
                'SELECT id FROM user_aliases WHERE user_id = ? AND recipient_pattern = ?',
                (token_user_id, query_pattern)
            )
            existing_alias = cursor.fetchone()

            if existing_alias:
                conn.execute('''
                    UPDATE user_aliases
                    SET display_name = ?, category = ?
                    WHERE id = ?
                ''', (new_narration, new_category, existing_alias['id']))
            else:
                conn.execute('''
                    INSERT INTO user_aliases (user_id, recipient_pattern, display_name, category)
                    VALUES (?, ?, ?, ?)
                ''', (token_user_id, query_pattern, new_narration, new_category))

        conn.commit()
        del _pending_bulk_updates[preview_id]

        return JSONResponse({
            "success": True,
            "updated_count": updated_count,
            "message": f"Successfully updated {updated_count} transactions and saved alias rule."
        })
    except Exception as e:
        conn.rollback()
        logger.error(f"Bulk update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")
    finally:
        conn.close()

@app.put("/api/transactions/{user_id}/{tx_id}")
async def update_transaction_name(user_id: str, tx_id: int, payload: dict = Body(...), req: Request = None):
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_db()
    try:
        new_name = payload.get('narration')
        if not new_name:
            raise HTTPException(status_code=400, detail="Missing name")
            
        conn.execute('''
            UPDATE transactions SET narration = ? WHERE id = ? AND user_id = ?
        ''', (new_name, tx_id, user_id))
        conn.commit()
        return JSONResponse({"success": True})
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating transaction name: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.put("/api/aliases/{user_id}/rename-group")
async def rename_alias_group(user_id: str, payload: dict = Body(...), req: Request = None):
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_db()
    try:
        old_name = payload.get('old_name')
        new_name = payload.get('new_name')
        new_category = payload.get('category', 'General')
        
        if not old_name or not new_name:
            raise HTTPException(status_code=400, detail="Missing names")
            
        cursor = conn.execute('''
            UPDATE user_aliases 
            SET display_name = ?, category = ?
            WHERE user_id = ? AND display_name = ?
        ''', (new_name, new_category, user_id, old_name))
        
        conn.commit()
        return JSONResponse({"success": True, "updated_count": cursor.rowcount})
    except Exception as e:
        conn.rollback()
        logger.error(f"Error renaming alias group: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/aliases/{user_id}/{alias_id}")
async def delete_alias(user_id: str, alias_id: int, req: Request):
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        conn.execute(
            'DELETE FROM user_aliases WHERE id = ? AND user_id = ?',
            (alias_id, user_id)
        )
        conn.commit()
        return JSONResponse({"success": True})
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete alias")
    finally:
        conn.close()


@app.delete("/api/aliases/{user_id}/transaction/{transaction_id}")
async def remove_transaction_from_alias(user_id: str, transaction_id: int, request: Request, category: Optional[str] = None):
    token_user_id = await get_current_user_id(request)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    conn = get_db()
    try:
        tx = conn.execute('''
            SELECT original_narration, narration, cleaned_narration
            FROM transactions
            WHERE id = ? AND user_id = ?
        ''', (transaction_id, user_id)).fetchone()

        if not tx:
            return {"success": False, "error": "Transaction not found"}

        cleaned = tx['cleaned_narration']
        original = cleaned if cleaned else (tx['original_narration'] or tx['narration'])
        new_category = category if category else 'Uncategorized'
        conn.execute('''
            UPDATE transactions
            SET narration = ?, category = ?
            WHERE id = ? AND user_id = ?
        ''', (original, new_category, transaction_id, user_id))

        conn.commit()
        return {"success": True, "message": "Transaction removed from alias", "category": new_category}
    finally:
        conn.close()


# ============ ONBOARDING GAPS ENDPOINTS ============

# Build a module-level map of bank name → provides_balance flag
# Evaluated once at load so detect_onboarding_gaps has O(1) lookup.
_BANK_PROVIDES_BALANCE = {}
for _ParserClass in PARSER_CLASSES:
    _p = _ParserClass()
    _BANK_PROVIDES_BALANCE[_p.BANK_NAME] = getattr(_p, 'PROVIDES_BALANCE', False)


def detect_onboarding_gaps(tx_accounts, anchored_accounts):
    """Detect accounts needing configuration: missing account number or anchor balance.

    Args:
        tx_accounts: List of dicts with keys bank, account_last4, has_account.
        anchored_accounts: Set of (bank, last4) tuples that already have anchor balances.

    Returns:
        Tuple of (gaps_list, total_unique_accounts). Each gap dict describes
        whether the account needs an account number and/or an anchor balance.
    """
    gaps = []
    seen = set()

    for acct in tx_accounts:
        bank  = acct['bank']
        last4 = acct.get('account_last4')
        key   = (bank, last4)

        if key in seen:
            continue
        seen.add(key)

        has_account = bool(acct.get('has_account'))
        # Use the parser's PROVIDES_BALANCE flag instead of the buggy balance_after column
        provides_balance = _BANK_PROVIDES_BALANCE.get(bank, False)

        needs_account_number = not has_account
        # If the bank doesn't provide a balance in emails, it ALWAYS needs an anchor
        needs_anchor = (not provides_balance) and (key not in anchored_accounts)

        if needs_account_number or needs_anchor:
            gaps.append({
                "bank":                 bank,
                "account_last4":        last4,
                "needs_account_number": needs_account_number,
                "needs_anchor":         needs_anchor,
                "provides_balance":     provides_balance,
            })

    return gaps, len(seen)


@app.get("/api/onboarding-gaps/{user_id}")
async def get_onboarding_gaps(user_id: str, req: Request):
    """Return all accounts that still need account numbers or anchor balances."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        # Aggregate per (bank, last4) to see what info is already stored
        cursor = conn.execute('''
            SELECT 
                bank,
                account_last4,
                MAX(CASE WHEN account_last4 IS NOT NULL AND account_last4 != '' AND account_last4 != '0000' THEN 1 ELSE 0 END) as has_account,
                MAX(CASE WHEN balance_after IS NOT NULL AND balance_after != 0 THEN 1 ELSE 0 END) as has_balance
            FROM transactions
            WHERE user_id = ?
            GROUP BY bank, account_last4
        ''', (user_id,))
        tx_accounts = [dict(r) for r in cursor.fetchall()]

        cursor = conn.execute('''
            SELECT DISTINCT bank, account_last4
            FROM account_balances
            WHERE user_id = ? AND is_anchor = 1
        ''', (user_id,))
        anchored = {(r['bank'], r['account_last4']) for r in cursor.fetchall()}

        gaps, total = detect_onboarding_gaps(tx_accounts, anchored)
        return JSONResponse({"success": True, "gaps": gaps, "total_accounts": total})
    except Exception as e:
        logger.error(f"Error getting onboarding gaps: {e}")
        raise HTTPException(status_code=500, detail="Failed to get onboarding gaps")
    finally:
        conn.close()


@app.post("/api/onboarding-gaps/{user_id}/resolve")
async def resolve_onboarding_gaps(user_id: str, req: Request):
    """Apply user-supplied account numbers and anchor balances to close onboarding gaps."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    balance_manager = BalanceManager(conn)
    try:
        data = await req.json()
        resolutions = data.get("resolutions", [])

        for item in resolutions:
            bank       = item.get("bank")
            old_last4  = item.get("old_last4")
            new_last4  = str(item.get("new_last4", ""))[-4:] if item.get("new_last4") else old_last4
            anchor_bal = item.get("anchor_balance")

            logger.info(f"Resolving gap for {bank} | old_last4: '{old_last4}' | new_last4: '{new_last4}' | anchor: {anchor_bal}")

            # Bulk-update transactions AND account_balances where last4 was missing
            if new_last4:
                conn.execute('''
                    UPDATE transactions
                    SET account_last4 = ?
                    WHERE user_id = ? AND bank = ?
                    AND (account_last4 IS NULL OR account_last4 = '' OR account_last4 = '0000')
                ''', (new_last4, user_id, bank))
                
                conn.execute('''
                    UPDATE account_balances
                    SET account_last4 = ?
                    WHERE user_id = ? AND bank = ?
                    AND (account_last4 IS NULL OR account_last4 = '' OR account_last4 = '0000')
                ''', (new_last4, user_id, bank))

            # ✅ NEW CODE (Only touches banks that actually need an anchor)
            # If the key "anchor_balance" is in the payload, the bank needs it.
            if "anchor_balance" in item:
                anchor_bal = item.get("anchor_balance")
                
                # If the user skipped, it will be None. Force it to 0.0.
                if anchor_bal is None:
                    anchor_bal = 0.0

                balance_manager.set_initial_balance(
                    user_id=user_id,
                    bank=bank,
                    account_last4=new_last4 or old_last4,
                    balance=float(anchor_bal)
                )

        conn.commit()
        return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"Gap resolution error: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to resolve onboarding gaps")
    finally:
        conn.close()


# ============ CLOUD SYNC TOGGLE ============

@app.get("/api/cloud-sync/{user_id}")
async def get_cloud_sync(user_id: str, req: Request):
    """Read the user's cloud sync preference (ON/OFF)."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        cursor = conn.execute('SELECT cloud_sync FROM user_prefs WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        return {"success": True, "cloud_sync": bool(row['cloud_sync']) if row else True}
    except Exception:
        return {"success": True, "cloud_sync": True}
    finally:
        conn.close()


@app.post("/api/cloud-sync/{user_id}/request-delete")
async def request_cloud_sync_delete(user_id: str, req: Request):
    """Generate a 60-second confirmation token before allowing data deletion."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token_data = f"{user_id}:{int(time.time())}"
    token = hashlib.sha256(token_data.encode()).hexdigest()[:32]
    if not hasattr(app.state, 'delete_tokens'):
        app.state.delete_tokens = {}
    app.state.delete_tokens[token] = {
        'user_id': user_id,
        'created_at': time.time(),
        'expires_at': time.time() + 60
    }
    return {"success": True, "confirmation_token": token, "expires_in": 60}


@app.post("/api/cloud-sync/{user_id}")
async def set_cloud_sync(user_id: str, request: CloudSyncToggle, req: Request):
    """Toggle cloud sync ON/OFF. Turning OFF purges all server-side user data."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        # Upsert: insert or update the single preference row
        conn.execute('''
            INSERT INTO user_prefs (user_id, cloud_sync, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET cloud_sync = ?, updated_at = datetime('now')
        ''', (user_id, int(request.cloud_sync), int(request.cloud_sync)))
        conn.commit()

        # SECURITY: When sync is disabled, require confirmation token before purging user data
        if not request.cloud_sync:
            confirmation_token = req.headers.get("X-Delete-Confirmation")
            if not confirmation_token:
                raise HTTPException(
                    status_code=400,
                    detail="Data deletion requires confirmation. Call /api/cloud-sync/{user_id}/request-delete first."
                )
            if not hasattr(app.state, 'delete_tokens'):
                raise HTTPException(status_code=400, detail="Invalid confirmation token")
            token_data = app.state.delete_tokens.get(confirmation_token)
            if not token_data or token_data['user_id'] != user_id:
                raise HTTPException(status_code=400, detail="Invalid confirmation token")
            if time.time() > token_data['expires_at']:
                del app.state.delete_tokens[confirmation_token]
                raise HTTPException(status_code=400, detail="Confirmation token expired")
            del app.state.delete_tokens[confirmation_token]
            conn.execute('DELETE FROM transactions WHERE user_id = ?', (user_id,))
            conn.execute('DELETE FROM account_balances WHERE user_id = ?', (user_id,))
            conn.execute('DELETE FROM user_aliases WHERE user_id = ?', (user_id,))
            conn.commit()

        return {"success": True, "cloud_sync": request.cloud_sync}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to update cloud sync preference")
    finally:
        conn.close()


# ============ ONBOARDING AUDIT DATES ============

@app.get("/api/user/onboarding-dates/{user_id}")
async def get_onboarding_dates(user_id: str, req: Request):
    """Retrieve the onboarding date window used for historical transaction audit."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        cursor = conn.execute(
            'SELECT onboarding_start_date, onboarding_end_date FROM users WHERE user_id = ?',
            (user_id,)
        )
        row = cursor.fetchone()
        return {
            "success": True,
            "start_date": row['onboarding_start_date'] if row else None,
            "end_date": row['onboarding_end_date'] if row else None,
            "has_onboarding": bool(row and row['onboarding_start_date'] and row['onboarding_end_date'])
        }
    except Exception as e:
        logger.error(f"Error getting onboarding dates: {e}")
        return {"success": True, "start_date": None, "end_date": None, "has_onboarding": False}
    finally:
        conn.close()


@app.post("/api/user/onboarding-dates/{user_id}")
async def set_onboarding_dates(user_id: str, request: OnboardingDatesRequest, req: Request):
    """Set or update the onboarding date window for historical audit."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    conn = get_db()
    try:
        conn.execute(
            'UPDATE users SET onboarding_start_date = ?, onboarding_end_date = ? WHERE user_id = ?',
            (request.start_date, request.end_date, user_id)
        )
        conn.commit()
        return {"success": True, "start_date": request.start_date, "end_date": request.end_date}
    except Exception as e:
        conn.rollback()
        logger.error(f"Error setting onboarding dates: {e}")
        raise HTTPException(status_code=500, detail="Failed to set onboarding dates")
    finally:
        conn.close()


# ============ DATA EXPORT / IMPORT ============

@app.get("/api/data/export/{user_id}")
async def export_user_data(user_id: str, req: Request):
    """Export all user data (transactions, balances, aliases) as a JSON payload.

    Only the latest balance per account is included (using a MAX(last_updated) subquery).
    """
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not check_rate_limit(get_client_ip(req), max_attempts=15, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")
    conn = get_db()
    try:
        tx_cursor = conn.execute(
            'SELECT bank, tx_type, amount, balance_after, narration, account_last4, timestamp, category '
            'FROM transactions WHERE user_id = ? ORDER BY timestamp', (user_id,)
        )
        transactions = [dict(r) for r in tx_cursor.fetchall()]

        # Select only the latest balance per account (subquery with MAX last_updated)
        bal_cursor = conn.execute(
            'SELECT bank, account_last4, balance, last_updated, is_anchor '
            'FROM account_balances WHERE user_id = ? AND (user_id, bank, account_last4, last_updated) IN '
            '(SELECT user_id, bank, account_last4, MAX(last_updated) FROM account_balances WHERE user_id = ? GROUP BY user_id, bank, account_last4)',
            (user_id, user_id)
        )
        balances = [dict(r) for r in bal_cursor.fetchall()]

        alias_cursor = conn.execute(
            'SELECT recipient_pattern, display_name, category, exact_match FROM user_aliases WHERE user_id = ?', (user_id,)
        )
        aliases = []
        for row in alias_cursor.fetchall():
            alias_dict = dict(row)
            alias_dict['exact_match'] = bool(alias_dict.get('exact_match', 0))
            aliases.append(alias_dict)

        return {
            "success": True,
            "transactions": transactions,
            "balances": balances,
            "aliases": aliases
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to export data")
    finally:
        conn.close()


@app.post("/api/data/import/{user_id}")
async def import_user_data(user_id: str, request: DataImportRequest, req: Request):
    """Import a previously exported data payload into the user's account."""
    token_user_id = await get_current_user_id(req)
    if not token_user_id or token_user_id != user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not check_rate_limit(get_client_ip(req), max_attempts=15, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute.")
    conn = get_db()
    balance_manager = BalanceManager(conn)
    try:
        for tx in request.transactions:
            conn.execute(
                'INSERT INTO transactions (user_id, bank, tx_type, amount, balance_after, narration, account_last4, timestamp, category) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    user_id, tx.get('bank'), tx.get('tx_type'), tx.get('amount'),
                    tx.get('balance_after'), tx.get('narration'), tx.get('account_last4'),
                    tx.get('timestamp'), tx.get('category', 'other')
                )
            )

        for bal in request.balances:
            balance_manager.set_initial_balance(
                user_id=user_id,
                bank=bal.get('bank'),
                account_last4=bal.get('account_last4', '0000'),
                balance=float(bal.get('balance', 0))
            )

        for alias in request.aliases:
            exact_match = 1 if alias.get('exact_match', False) else 0
            conn.execute(
                'INSERT OR REPLACE INTO user_aliases (user_id, recipient_pattern, display_name, category, exact_match) '
                'VALUES (?, ?, ?, ?, ?)',
                (user_id, alias.get('recipient_pattern'), alias.get('display_name'), alias.get('category', 'General'), exact_match)
            )

        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to import data")
    finally:
        conn.close()


# ============ FRONTEND STATIC FILES ============

import pathlib

# Resolve the built frontend dist directory relative to this file
FRONTEND_DIR = pathlib.Path(__file__).parent.parent / "frontend" / "dist"

# Only mount the SPA if the build output directory exists
if FRONTEND_DIR.exists():
    # Serve built assets (JS/CSS) from the /assets sub-path
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.exception_handler(404)
    async def spa_fallback(request: Request, exc):
        """Catch-all: serve index.html for non-API routes (SPA client-side routing).

        Lets the frontend router handle paths like /dashboard, /settings, etc.
        API and health-check routes return standard JSON 404.
        """
        if request.url.path.startswith("/api/") or request.url.path.startswith("/health"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        # SECURITY: path traversal is blocked below in serve_frontend
        return FileResponse(str(FRONTEND_DIR / "index.html"), media_type="text/html")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve static files from the dist directory, falling back to index.html for SPA routes."""
        resolved = (FRONTEND_DIR / full_path).resolve()
        # SECURITY: prevent directory traversal outside FRONTEND_DIR
        if not str(resolved).startswith(str(FRONTEND_DIR.resolve())):
            raise HTTPException(status_code=404)
        if resolved.exists() and resolved.is_file():
            return FileResponse(str(resolved))
        # SPA fallback: any unknown path returns index.html so Vue/React router can handle it
        return FileResponse(str(FRONTEND_DIR / "index.html"), media_type="text/html")