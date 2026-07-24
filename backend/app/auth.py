"""
auth.py — JWT authentication, OAuth token management, and Fernet-based
email password encryption for Mirror.ng.

Handles user identity via httpOnly cookies with Bearer header fallback.
Email credentials are encrypted at rest using a separate Fernet key.
"""
import os
import logging
import uuid
import base64
from datetime import datetime, timedelta
from typing import Optional
import jwt
from cryptography.fernet import Fernet
from fastapi import Request, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from .database import get_db

logger = logging.getLogger(__name__)

# SECURITY: JWT signing key — must be a strong random secret set in env
SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# ── Fernet encryption for email passwords ──────────────────────────
# SECURITY: Separate key from JWT_SECRET; used to encrypt OAuth tokens
# at rest in the database. Loss of this key makes stored tokens undecryptable.
EMAIL_ENCRYPTION_KEY = os.getenv("EMAIL_ENCRYPTION_KEY")
if not EMAIL_ENCRYPTION_KEY:
    raise RuntimeError("EMAIL_ENCRYPTION_KEY environment variable is required")

_fernet = Fernet(EMAIL_ENCRYPTION_KEY.encode() if isinstance(EMAIL_ENCRYPTION_KEY, str) else EMAIL_ENCRYPTION_KEY)

def encrypt_email_password(plaintext: str) -> str:
    """Encrypt a plaintext string using the application-wide Fernet key.

    Args:
        plaintext: The raw credential string to encrypt.

    Returns:
        Base64-encoded ciphertext as a UTF-8 string.
    """
    return _fernet.encrypt(plaintext.encode()).decode()

def decrypt_email_password(encrypted: str) -> Optional[str]:
    """Decrypt a Fernet-encrypted credential back to plaintext.

    Args:
        encrypted: The base64 ciphertext previously produced by
                   encrypt_email_password.  May be empty or None.

    Returns:
        Decrypted plaintext string, or None if the token is empty,
        the key has been rotated (InvalidToken), or any other error occurs.
    """
    if not encrypted:
        return None
    from cryptography.fernet import InvalidToken
    try:
        return _fernet.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        # SECURITY: Silent failure prevents info leak; log for operator awareness
        logger.warning("Failed to decrypt email password — key may have been rotated")
        return None
    except Exception as e:
        logger.error(f"Unexpected error decrypting email password: {e}")
        return None

security = HTTPBearer(auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT with a unique ID and expiry claim.

    Args:
        data: Payload claims (at minimum should include 'user_id').
        expires_delta: Custom lifetime; defaults to ACCESS_TOKEN_EXPIRE_DAYS.

    Returns:
        Encoded JWT string suitable for an httpOnly cookie or Bearer header.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": str(uuid.uuid4())
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT without verifying issuer/audience.

    Args:
        token: Raw JWT string.

    Returns:
        Decoded payload dict on success, None on any decoding or
        signature validation failure.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def _is_jti_blacklisted(jti: str) -> bool:
    """Check whether a JWT identifier has been revoked (logout)."""
    conn = get_db()
    cursor = conn.execute('SELECT jti FROM token_blacklist WHERE jti = ?', (jti,))
    blacklisted = cursor.fetchone() is not None
    conn.close()
    return blacklisted


async def get_current_user_id(request: Request) -> Optional[str]:
    """Extract the authenticated user_id from the request.

    Preference order: httpOnly cookie (mirror_token) first, then
    Authorization: Bearer header.  This dual-path supports a gradual
    migration from Bearer-only to cookie-based auth.

    Args:
        request: Incoming FastAPI request.

    Returns:
        User ID string if authenticated, None otherwise.
    """
    # SECURITY: httpOnly cookie is not accessible to JS, reducing XSS risk
    token = request.cookies.get("mirror_token")
    if token:
        payload = decode_access_token(token)
        if payload:
            jti = payload.get("jti")
            if jti and _is_jti_blacklisted(jti):
                return None
            return payload.get("user_id")

    # Fallback to Authorization header (migration period)
    auth: Optional[HTTPAuthorizationCredentials] = await security(request)
    if not auth:
        return None
    payload = decode_access_token(auth.credentials)
    if payload is None:
        return None
    jti = payload.get("jti")
    if jti and _is_jti_blacklisted(jti):
        return None
    return payload.get("user_id")


async def require_user_id(request: Request) -> str:
    """Guarantee an authenticated user_id or raise 401.

    Wraps get_current_user_id and immediately rejects unauthenticated
    requests so route handlers can assume a valid user context.

    Args:
        request: Incoming FastAPI request.

    Returns:
        User ID string.

    Raises:
        HTTPException 401: No valid token was found.
    """
    user_id = await get_current_user_id(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

async def verify_admin(admin_key: str = Security(admin_key_header)) -> str:
    """Verify admin key from X-Admin-Key header."""
    admin_key_env = os.getenv("ADMIN_KEY")
    if not admin_key_env:
        raise HTTPException(status_code=500, detail="Admin authentication not configured")
    if not admin_key or admin_key != admin_key_env:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return admin_key
