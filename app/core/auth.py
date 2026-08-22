"""
app/core/auth.py
================
JWT Authentication, Password Hashing, Disposable Email Filter & OTP Verification.
"""
import uuid
import os
import random
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

try:
    from jose import JWTError, jwt
    _JOSE_AVAILABLE = True
except ImportError:
    _JOSE_AVAILABLE = False
    logger.warning("python-jose not installed. JWT auth disabled.")

try:
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
    _PASSLIB_AVAILABLE = True
except ImportError:
    _PASSLIB_AVAILABLE = False
    logger.warning("passlib not installed.")

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
    if not _PASSLIB_AVAILABLE:
        raise AuthError("Password hashing unavailable. Install passlib[bcrypt].", 503)
    truncated = plain_password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return _pwd_context.hash(truncated)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not _PASSLIB_AVAILABLE:
        return False
    try:
        truncated = plain_password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
        return _pwd_context.verify(truncated, hashed_password)
    except Exception:
        return False


def create_access_token(
    user_id: str,
    email: str,
    name: str,
    role: str,
    is_guest: bool = False,
    expire_minutes: Optional[int] = None,
) -> str:
    if not _JOSE_AVAILABLE:
        raise AuthError("JWT library unavailable. Install python-jose[cryptography].", 503)
    expires_delta = timedelta(minutes=expire_minutes or (
        GUEST_TOKEN_EXPIRE_MINUTES if is_guest else ACCESS_TOKEN_EXPIRE_MINUTES
    ))
    expire = datetime.utcnow() + expires_delta
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "role": role,
        "is_guest": is_guest,
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    if not _JOSE_AVAILABLE:
        raise AuthError("JWT library unavailable.", 503)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
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
    return _JOSE_AVAILABLE and _PASSLIB_AVAILABLE
