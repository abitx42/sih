"""
app/core/auth.py
================
JWT Authentication, Password Hashing, Disposable Email Filter & OTP Verification.
Supports modern PyJWT and direct bcrypt, with graceful fallback to jose/passlib.
"""
import uuid
import os
import random
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# ── JWT Backend Support (PyJWT preferred, jose fallback) ─────────────────────
try:
    import jwt as pyjwt
    _JWT_AVAILABLE = True
    _JWT_BACKEND = "pyjwt"
except ImportError:
    try:
        from jose import jwt as pyjwt
        _JWT_AVAILABLE = True
        _JWT_BACKEND = "jose"
    except ImportError:
        _JWT_AVAILABLE = False
        _JWT_BACKEND = None
        logger.warning("No JWT library found (PyJWT or python-jose). JWT auth disabled.")

# ── Password Hashing Support (bcrypt direct preferred, passlib fallback) ─────
try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False

try:
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    _PASSLIB_AVAILABLE = True
except ImportError:
    _PASSLIB_AVAILABLE = False

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "truth-lens-super-secret-key-change-in-production-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
GUEST_TOKEN_EXPIRE_MINUTES = 120

# ── Blocked Disposable / Temporary Email Domains ─────────────────────────────
DISPOSABLE_DOMAINS = {
    "mailinator.com", "10minutemail.com", "guerrillamail.com", "tempmail.com",
    "throwawaymail.com", "sharklasers.com", "yopmail.com", "dispostable.com",
    "getairmail.com", "maildrop.cc", "trashmail.com", "mohmal.com",
    "crazymailing.com", "mytemp.email", "nada.ltd", "burnermail.io",
    "fakemailgenerator.com", "temp-mail.org", "generator.email", "emailondeck.com",
    "inboxkitten.com", "mailsac.com", "harakirimail.com", "meltmail.com",
    "minuteinbox.com", "tmail.ws", "tempmailaddress.com", "throwawayemail.com",
    "temporary-mail.net", "dropmail.me", "fakemail.net", "getnada.com",
    "incognitomail.org", "internxt.com/temporary-email", "jetable.org", "kasmail.com",
    "mytempmail.com", "noclickemail.com", "oneoffmail.com", "owlymail.com",
    "receivemail.org", "sharklasers.net", "spambox.us", "superrito.com",
    "teleworm.us", "trashmail.net", "uggsrock.com", "wegwerfmail.de",
    "zippymail.info", "armyspy.com", "cuvox.de", "dayrep.com", "einrot.com",
    "fleckens.hu", "gustr.com", "jourrapide.com", "rhyta.com", "superrito.com"
}

# ── Trusted Popular Email Providers & TLDs ────────────────────────────────────
POPULAR_TRUSTED_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "apple.com", "proton.me", "protonmail.com", "zoho.com", "aol.com",
    "live.com", "msn.com", "mail.com", "gmx.com", "yandex.com", "fastmail.com"
}


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def validate_email_domain(email: str) -> Tuple[bool, str]:
    """
    Validates email address syntax and blocks disposable / temporary domains.
    Returns (is_valid, error_reason).
    """
    email = email.strip().lower()
    if not email or "@" not in email:
        return False, "Invalid email address format."

    parts = email.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return False, "Invalid email address format."

    domain = parts[1]

    # Check against disposable domain blocklist
    if domain in DISPOSABLE_DOMAINS or any(domain.endswith("." + d) for d in DISPOSABLE_DOMAINS):
        return False, f"Temporary/disposable email domain '@{domain}' is blocked. Please use a permanent email (Gmail, Outlook, Yahoo, iCloud, university, or corporate domain)."

    # Reject common disposable keywords in domain
    if any(k in domain for k in ["tempmail", "disposable", "fakeinbox", "trashmail", "throwaway", "guerrilla"]):
        return False, "Disposable email addresses are not permitted."

    # Validate basic domain format
    if "." not in domain or len(domain.split(".")[-1]) < 2:
        return False, "Invalid domain extension."

    return True, ""


def generate_verification_code() -> str:
    """Generates a secure 6-digit numeric verification code."""
    return f"{random.randint(100000, 999999)}"


def hash_password(plain_password: str) -> str:
    if _BCRYPT_AVAILABLE:
        truncated = plain_password.encode("utf-8")[:72]
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(truncated, salt).decode("utf-8")
    elif _PASSLIB_AVAILABLE:
        return _pwd_context.hash(plain_password[:72])
    raise AuthError("Password hashing unavailable. Install bcrypt or passlib.", 503)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if _BCRYPT_AVAILABLE:
        try:
            truncated = plain_password.encode("utf-8")[:72]
            return bcrypt.checkpw(truncated, hashed_password.encode("utf-8"))
        except Exception:
            pass
    if _PASSLIB_AVAILABLE:
        try:
            return _pwd_context.verify(plain_password[:72], hashed_password)
        except Exception:
            pass
    return False


def create_access_token(
    user_id: str,
    email: str,
    name: str,
    role: str,
    is_guest: bool = False,
    expire_minutes: Optional[int] = None,
) -> str:
    if not _JWT_AVAILABLE:
        raise AuthError("JWT library unavailable. Install PyJWT or python-jose.", 503)
    expires_delta = timedelta(minutes=expire_minutes or (
        GUEST_TOKEN_EXPIRE_MINUTES if is_guest else ACCESS_TOKEN_EXPIRE_MINUTES
    ))
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "role": role,
        "is_guest": is_guest,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
    }
    return pyjwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    if not _JWT_AVAILABLE:
        raise AuthError("JWT library unavailable.", 503)
    try:
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception as e:
        raise AuthError(f"Invalid or expired token: {e}", 401)


def create_guest_token() -> str:
    guest_id = f"GUEST-{uuid.uuid4().hex[:8].upper()}"
    return create_access_token(
        user_id=guest_id,
        email="guest@truthlens.local",
        name="Guest Investigator",
        role="GUEST",
        is_guest=True,
    )


def is_auth_available() -> bool:
    return _JWT_AVAILABLE and (_BCRYPT_AVAILABLE or _PASSLIB_AVAILABLE)


def get_current_user_optional(authorization: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Extracts user claims from Authorization header if present and valid; returns None otherwise."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return decode_token(authorization[7:])
    except AuthError:
        return None


def get_current_user(authorization: Optional[str] = None) -> Dict[str, Any]:
    """Enforces valid JWT Bearer token on protected endpoints."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("Authorization header missing or invalid", 401)
    return decode_token(authorization[7:])

