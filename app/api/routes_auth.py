"""
app/api/routes_auth.py
Authentication API routes: register, login, me, logout, accept-terms, guest.
"""
import uuid
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from app.database import get_db
from app.core.auth import (
    hash_password, verify_password,
    create_access_token, create_guest_token,
    decode_token, AuthError, is_auth_available
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    data_consent: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str


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
        "message": "Authentication system operational" if is_auth_available() else "Auth dependencies not installed — run: pip install 'python-jose[cryptography]' 'passlib[bcrypt]'"
    }


@router.post("/register")
def register(body: RegisterRequest):
    if not is_auth_available():
        raise HTTPException(status_code=503, detail="Auth system unavailable. Install python-jose and passlib.")
    name = body.name.strip()
    email = body.email.strip().lower()
    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    if not body.password or len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    with get_db() as conn:
        existing = conn.execute("SELECT user_id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        user_id = f"USR-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.utcnow().isoformat() + "Z"
        hashed = hash_password(body.password)
        conn.execute("""
            INSERT INTO users (user_id, email, name, password_hash, role, created_at, data_consent, data_consent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, email, name, hashed, "INVESTIGATOR", now,
               1 if body.data_consent else 0, now if body.data_consent else None))
    token = create_access_token(user_id=user_id, email=email, name=name, role="INVESTIGATOR")
    logger.info(f"New user registered: {email} ({user_id})")
    return {
        "success": True,
        "message": "Account created successfully",
        "token": token,
        "user": {"user_id": user_id, "name": name, "email": email, "role": "INVESTIGATOR", "tc_accepted": False}
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
            "tc_accepted": bool(user.get("tc_accepted", 0))
        }
    }


@router.post("/guest")
def guest_access():
    token = create_guest_token()
    return {
        "success": True, "token": token,
        "user": {"user_id": None, "name": "Guest Investigator", "email": None, "role": "GUEST", "tc_accepted": False},
        "message": "Guest session active. Sign in to save your case history."
    }


@router.get("/me")
def get_me(authorization: Optional[str] = Header(None)):
    payload = _get_user_from_token(authorization)
    if payload.get("is_guest"):
        return {"user_id": payload["sub"], "name": payload["name"], "email": None, "role": "GUEST", "tc_accepted": False, "is_guest": True}
    with get_db() as conn:
        user = conn.execute(
            "SELECT user_id, name, email, role, tc_accepted, created_at, last_login FROM users WHERE user_id = ?",
            (payload["sub"],)
        ).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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
    return {"success": True, "message": "Terms accepted. Thank you!"}


@router.post("/logout")
def logout(authorization: Optional[str] = Header(None)):
    return {"success": True, "message": "Logged out. Please discard your token."}
