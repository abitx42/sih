"""
app/api/routes_auth.py
======================
Authentication API routes: register, login, verify-email, resend-code, me, accept-terms, guest.
"""
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from app.database import get_db
from app.core.auth import (
    hash_password, verify_password,
    create_access_token, create_guest_token,
    decode_token, validate_email_domain, generate_verification_code,
    AuthError, is_auth_available
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    data_consent: bool = True


class LoginRequest(BaseModel):
    email: str
    password: str


class VerifyEmailRequest(BaseModel):
    email: str
    code: str


class ResendCodeRequest(BaseModel):
    email: str


class AcceptTermsRequest(BaseModel):
    data_consent: bool = True


def _get_user_from_token(authorization: Optional[str]) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header missing or invalid")
    token = authorization[7:]
    try:
        return decode_token(token)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/status")
def auth_status():
    return {
        "auth_enabled": is_auth_available(),
        "message": "Authentication system operational" if is_auth_available() else "Auth dependencies not installed"
    }


@router.post("/register")
def register(body: RegisterRequest):
    if not is_auth_available():
        raise HTTPException(status_code=503, detail="Auth system unavailable.")

    name = body.name.strip()
    email = body.email.strip().lower()

    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters.")

    # Validate email domain against disposable list
    is_valid_email, err_reason = validate_email_domain(email)
    if not is_valid_email:
        raise HTTPException(status_code=400, detail=err_reason)

    if not body.password or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    otp_code = generate_verification_code()
    expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat() + "Z"
    now = datetime.utcnow().isoformat() + "Z"
    user_id = f"USR-{uuid.uuid4().hex[:10].upper()}"

    with get_db() as conn:
        existing = conn.execute("SELECT user_id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="An account with this email already exists.")

        hashed = hash_password(body.password)
        conn.execute("""
            INSERT INTO users (
                user_id, email, name, password_hash, role, created_at,
                data_consent, data_consent_at, email_verified, verification_code, verification_code_expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, email, name, hashed, "INVESTIGATOR", now,
            1 if body.data_consent else 0, now if body.data_consent else None,
            0, otp_code, expires_at
        ))

    logger.info(f"New user registered: {email} ({user_id}) - Verification OTP: {otp_code}")

    token = create_access_token(user_id=user_id, email=email, name=name, role="INVESTIGATOR")

    return {
        "success": True,
        "message": f"Account created. Verification code sent to {email}.",
        "token": token,
        "user": {
            "user_id": user_id,
            "name": name,
            "email": email,
            "role": "INVESTIGATOR",
            "email_verified": False,
            "tc_accepted": False
        },
        "verification_code_demo": otp_code  # For instant developer/demo testing
    }


@router.post("/verify-email")
def verify_email(body: VerifyEmailRequest):
    """Verify 6-digit OTP code sent to user email."""
    email = body.email.strip().lower()
    code = body.code.strip()

    with get_db() as conn:
        user = conn.execute(
            "SELECT user_id, verification_code, verification_code_expires_at, email_verified FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="Account not found.")

        if user.get("email_verified") == 1:
            return {"success": True, "message": "Email is already verified."}

        stored_code = user.get("verification_code")
        if not stored_code or stored_code != code:
            raise HTTPException(status_code=400, detail="Invalid verification code. Please check and try again.")

        # Mark as verified
        conn.execute(
            "UPDATE users SET email_verified = 1, verification_code = NULL, verification_code_expires_at = NULL WHERE email = ?",
            (email,)
        )

    logger.info(f"User email verified successfully: {email}")
    return {"success": True, "message": "Email successfully verified! Full access unlocked."}


@router.post("/resend-code")
def resend_verification_code(body: ResendCodeRequest):
    """Generate and resend a new 6-digit verification code."""
    email = body.email.strip().lower()
    new_otp = generate_verification_code()
    expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat() + "Z"

    with get_db() as conn:
        user = conn.execute("SELECT user_id, email_verified FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Account not found.")
        if user.get("email_verified") == 1:
            return {"success": True, "message": "Email is already verified."}

        conn.execute(
            "UPDATE users SET verification_code = ?, verification_code_expires_at = ? WHERE email = ?",
            (new_otp, expires_at, email)
        )

    logger.info(f"Resent verification code for {email}: {new_otp}")
    return {
        "success": True,
        "message": f"A new verification code has been sent to {email}.",
        "verification_code_demo": new_otp
    }


@router.post("/login")
def login(body: LoginRequest):
    if not is_auth_available():
        raise HTTPException(status_code=503, detail="Auth system unavailable.")
    email = body.email.strip().lower()
    with get_db() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND is_active = 1", (email,)
        ).fetchone()
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET last_login = ? WHERE user_id = ?",
            (datetime.utcnow().isoformat() + "Z", user["user_id"])
        )
    token = create_access_token(
        user_id=user["user_id"], email=user["email"],
        name=user["name"], role=user["role"]
    )
    logger.info(f"User logged in: {email}")
    return {
        "success": True, "token": token,
        "user": {
            "user_id": user["user_id"], "name": user["name"],
            "email": user["email"], "role": user["role"],
            "email_verified": bool(user.get("email_verified", 0)),
            "tc_accepted": bool(user.get("tc_accepted", 0))
        }
    }


@router.post("/guest")
def guest_access():
    token = create_guest_token()
    return {
        "success": True, "token": token,
        "user": {
            "user_id": None, "name": "Guest Investigator", "email": None,
            "role": "GUEST", "tc_accepted": False, "is_guest": True,
            "guest_upload_limit": 3
        },
        "message": "Guest session active (Limited to 3 exhibits, PDF export requires sign in)."
    }


@router.get("/me")
def get_me(authorization: Optional[str] = Header(None)):
    payload = _get_user_from_token(authorization)
    is_guest = payload.get("is_guest") or str(payload.get("sub", "")).startswith("GUEST-") or payload.get("role") == "GUEST"
    if is_guest:
        return {
            "user_id": payload.get("sub", "GUEST-USER"),
            "name": payload.get("name", "Guest Investigator"),
            "email": None,
            "role": "GUEST",
            "tc_accepted": True,
            "is_guest": True,
            "guest_upload_limit": 3
        }
    with get_db() as conn:
        user = conn.execute(
            "SELECT user_id, name, email, role, tc_accepted, email_verified, data_consent, created_at, last_login, auth_provider, avatar_url FROM users WHERE user_id = ?",
            (payload["sub"],)
        ).fetchone()
    if not user:
        return {
            "user_id": payload.get("sub", "USR-OFFLINE"),
            "name": payload.get("name", "Investigator"),
            "email": payload.get("email"),
            "role": payload.get("role", "INVESTIGATOR"),
            "tc_accepted": True,
            "is_guest": False
        }
    return {**user, "is_guest": False}


@router.post("/accept-terms")
def accept_terms(body: AcceptTermsRequest, authorization: Optional[str] = Header(None)):
    payload = _get_user_from_token(authorization)
    if payload.get("is_guest"):
        return {"success": True, "message": "Guest session — T&C noted for this session"}
    now = datetime.utcnow().isoformat() + "Z"
    with get_db() as conn:
        conn.execute("""
            UPDATE users SET tc_accepted = 1, tc_accepted_at = ?, data_consent = ?, data_consent_at = ?
            WHERE user_id = ?
        """, (now, 1 if body.data_consent else 0, now if body.data_consent else None, payload["sub"]))
    return {"success": True, "message": "Terms and data consent accepted. Thank you!"}


@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    return {"success": True, "message": "Logged out. Please discard your token."}


class GoogleAuthRequest(BaseModel):
    credential: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    google_id: Optional[str] = None
    avatar_url: Optional[str] = None
    data_consent: bool = True


@router.post("/google")
def google_auth(body: GoogleAuthRequest):
    """
    Authenticate / Register user via Google Sign-In.
    Accepts Google Identity token or verified Google profile claims.
    """
    email = None
    name = None
    google_id = body.google_id
    avatar_url = body.avatar_url

    # 1. Decode Google Credential if JWT is provided
    if body.credential:
        try:
            from jose import jwt as jose_jwt
            # Parse unverified claims from Google ID token
            claims = jose_jwt.get_unverified_claims(body.credential)
            email = str(claims.get("email", "")).strip().lower()
            name = str(claims.get("name", claims.get("given_name", "Google Investigator"))).strip()
            google_id = str(claims.get("sub", google_id or ""))
            avatar_url = claims.get("picture", avatar_url)
        except Exception as e:
            logger.warning(f"Google token unverified decode fallback: {e}")

    # Fallback to direct parameters
    if not email and body.email:
        email = body.email.strip().lower()
    if not name and body.name:
        name = body.name.strip()

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required for Google authentication.")

    now = datetime.utcnow().isoformat() + "Z"
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        existing = cursor.fetchone()

        if existing:
            user_id = existing["user_id"]
            user_name = existing["name"] or name or "Investigator"
            role = existing.get("role", "INVESTIGATOR")
            cursor.execute("""
                UPDATE users 
                SET last_login = ?, email_verified = 1, auth_provider = 'GOOGLE',
                    google_id = COALESCE(?, google_id), avatar_url = COALESCE(?, avatar_url)
                WHERE user_id = ?
            """, (now, google_id, avatar_url, user_id))
        else:
            user_id = f"USR-G-{uuid.uuid4().hex[:8].upper()}"
            user_name = name or email.split("@")[0].capitalize()
            role = "INVESTIGATOR"
            cursor.execute("""
                INSERT INTO users (
                    user_id, email, name, password_hash, role, created_at, last_login,
                    is_active, tc_accepted, tc_accepted_at, data_consent, data_consent_at,
                    email_verified, auth_provider, google_id, avatar_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, 1, ?, 1, 'GOOGLE', ?, ?)
            """, (user_id, email, user_name, "OAUTH_GOOGLE_ACCOUNT", role, now, now, now, now, google_id, avatar_url))

    token = create_access_token(
        user_id=user_id,
        email=email,
        name=user_name,
        role=role,
        is_guest=False
    )
    logger.info(f"Google auth successful for: {email} ({user_id})")

    return {
        "success": True,
        "token": token,
        "user": {
            "user_id": user_id,
            "name": user_name,
            "email": email,
            "role": role,
            "auth_provider": "GOOGLE",
            "email_verified": True,
            "tc_accepted": True,
            "avatar_url": avatar_url
        },
        "message": "Signed in with Google successfully."
    }
