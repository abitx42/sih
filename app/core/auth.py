"""
app/core/auth.py
JWT Authentication & Password Hashing for Truth Lens.
"""
import uuid
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

try:
    from jose import JWTError, jwt
    _JOSE_AVAILABLE = True
except ImportError:
    _JOSE_AVAILABLE = False
    logger.warning("python-jose not installed. JWT auth disabled. Run: pip install 'python-jose[cryptography]'")

try:
    from passlib.context import CryptContext
    # Use sha256_crypt as primary: passlib 1.7.x has bcrypt 4.x compatibility issues.
    # sha256_crypt is equally secure and has zero version friction.
    _pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
    _PASSLIB_AVAILABLE = True
except ImportError:
    _PASSLIB_AVAILABLE = False
    logger.warning("passlib not installed. Run: pip install 'passlib[bcrypt]'")

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "truth-lens-super-secret-key-change-in-production-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
GUEST_TOKEN_EXPIRE_MINUTES = 120


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def hash_password(plain_password: str) -> str:
    if not _PASSLIB_AVAILABLE:
        raise AuthError("Password hashing unavailable. Install passlib[bcrypt].", 503)
    # bcrypt has a 72-byte limit; truncate to avoid ValueError on newer bcrypt versions
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
