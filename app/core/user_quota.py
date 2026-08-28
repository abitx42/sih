"""
Per-user exhibit quantity and storage quotas.

Identity
--------
Authenticated JWT  →  email (or guest `sub`) is the stable quota key.
Unauthenticated    →  form `uploaded_by` string (API clients / pytest).

Tiers
-----
GUEST                   3 files,    10 MB each,    25 MB total
STANDARD               10 files,    25 MB each,    50 MB total   (Google / local investigator)
VERIFIED_INVESTIGATOR  50 files,   150 MB each,   500 MB total
ENTERPRISE_ADMIN     1000 files,  1000 MB each,  10 GB total
UNAUTHENTICATED       500 files,   150 MB each,     5 GB total   (no JWT — tests & raw API)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from app.core.auth import AuthError, decode_token
from app.database import get_db

logger = logging.getLogger(__name__)

QUOTA_TIERS: Dict[str, Dict[str, int]] = {
    "GUEST": {
        "max_file_size_mb": 10,
        "max_total_storage_mb": 25,
        "max_file_count": 3,
    },
    "STANDARD": {
        "max_file_size_mb": 25,
        "max_total_storage_mb": 50,
        "max_file_count": 10,
    },
    "VERIFIED_INVESTIGATOR": {
        "max_file_size_mb": 150,
        "max_total_storage_mb": 500,
        "max_file_count": 50,
    },
    "ENTERPRISE_ADMIN": {
        "max_file_size_mb": 1000,
        "max_total_storage_mb": 10000,
        "max_file_count": 1000,
    },
    "UNAUTHENTICATED": {
        "max_file_size_mb": 150,
        "max_total_storage_mb": 50000,
        "max_file_count": 50000,
    },
}

_MB = 1024 * 1024


def resolve_tier(role: Optional[str], is_guest: bool = False) -> str:
    if is_guest or (role or "").upper() == "GUEST":
        return "GUEST"
    role_u = (role or "").upper()
    if role_u in ("ADMIN", "ENTERPRISE_ADMIN", "SUPERADMIN"):
        return "ENTERPRISE_ADMIN"
    if role_u in ("VERIFIED_INVESTIGATOR", "SENIOR_INVESTIGATOR"):
        return "VERIFIED_INVESTIGATOR"
    if role_u in ("UNAUTHENTICATED", "ANONYMOUS"):
        return "UNAUTHENTICATED"
    return "STANDARD"


def identity_from_authorization(
    authorization: Optional[str],
    form_uploaded_by: str = "Digital Forensics Investigator",
) -> Dict[str, Any]:
    """
    Resolve the quota actor from a Bearer JWT when present.
    Falls back to the form officer name so unauthenticated API clients still work.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if token:
            try:
                payload = decode_token(token)
                sub = str(payload.get("sub") or "")
                role = str(payload.get("role") or "INVESTIGATOR")
                is_guest = bool(
                    payload.get("is_guest")
                    or sub.startswith("GUEST-")
                    or role.upper() == "GUEST"
                )
                email = (payload.get("email") or "").strip().lower() or None
                actor_key = sub if is_guest else (email or sub or form_uploaded_by)
                return {
                    "actor_key": actor_key,
                    "role": "GUEST" if is_guest else role,
                    "is_guest": is_guest,
                    "email": None if is_guest else email,
                    "name": payload.get("name") or form_uploaded_by,
                    "authenticated": True,
                    "user_id": sub or None,
                }
            except AuthError:
                logger.debug("Quota identity: invalid bearer token, using form actor")
            except Exception as exc:
                logger.debug("Quota identity: token parse failed (%s)", exc)

    actor = (form_uploaded_by or "anonymous").strip() or "anonymous"
    return {
        "actor_key": actor,
        "role": "UNAUTHENTICATED",
        "is_guest": False,
        "email": None,
        "name": actor,
        "authenticated": False,
        "user_id": None,
    }


def get_quota_usage(actor_key: str) -> Dict[str, int]:
    if not actor_key:
        return {"file_count": 0, "total_bytes": 0}
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS file_count,
                   COALESCE(SUM(file_size_bytes), 0) AS total_bytes
            FROM evidence
            WHERE quota_actor = ?
               OR (quota_actor IS NULL AND uploaded_by = ?)
            """,
            (actor_key, actor_key),
        ).fetchone()
    return {
        "file_count": int((row or {}).get("file_count") or 0),
        "total_bytes": int((row or {}).get("total_bytes") or 0),
    }


def _tier_bytes(limits: Dict[str, int]) -> Tuple[int, int, int]:
    return (
        limits["max_file_size_mb"] * _MB,
        limits["max_total_storage_mb"] * _MB,
        limits["max_file_count"],
    )


def check_user_quota(
    actor_key: str,
    role: Optional[str] = "INVESTIGATOR",
    is_guest: bool = False,
    incoming_bytes: int = 0,
    extra_files: int = 1,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Return (allowed, reason, usage_snapshot).
    `extra_files` is the number of exhibits about to be added (1 for single, N for a bulk pre-check).
    """
    tier_name = resolve_tier(role, is_guest)
    limits = QUOTA_TIERS[tier_name]
    usage = get_quota_usage(actor_key)
    max_file_bytes, max_total_bytes, max_count = _tier_bytes(limits)
    plan = tier_name.replace("_", " ").title()

    if incoming_bytes > max_file_bytes:
        return (
            False,
            (
                f"File exceeds the {limits['max_file_size_mb']} MB per-exhibit limit "
                f"for your {plan} plan."
            ),
            usage,
        )
    if usage["file_count"] + extra_files > max_count:
        return (
            False,
            (
                f"Exhibit quantity limit reached ({usage['file_count']}/{max_count} files "
                f"on the {plan} plan). Sign in with Google or use a verified investigator "
                f"account to raise this cap."
            ),
            usage,
        )
    if usage["total_bytes"] + incoming_bytes > max_total_bytes:
        used_mb = round(usage["total_bytes"] / _MB, 1)
        return (
            False,
            (
                f"Storage quota exceeded ({used_mb}/{limits['max_total_storage_mb']} MB "
                f"on the {plan} plan)."
            ),
            usage,
        )
    return True, "OK", usage


def build_quota_status(
    actor_key: str,
    role: Optional[str] = "INVESTIGATOR",
    is_guest: bool = False,
) -> Dict[str, Any]:
    tier_name = resolve_tier(role, is_guest)
    limits = QUOTA_TIERS[tier_name]
    usage = get_quota_usage(actor_key)
    max_file_bytes, max_total_bytes, max_count = _tier_bytes(limits)
    remaining_files = max(0, max_count - usage["file_count"])
    remaining_bytes = max(0, max_total_bytes - usage["total_bytes"])
    percent_files = round(100.0 * usage["file_count"] / max_count, 1) if max_count else 0.0
    percent_storage = (
        round(100.0 * usage["total_bytes"] / max_total_bytes, 1) if max_total_bytes else 0.0
    )
    return {
        "tier": tier_name,
        "limits": {
            "max_file_size_mb": limits["max_file_size_mb"],
            "max_file_size_bytes": max_file_bytes,
            "max_total_storage_mb": limits["max_total_storage_mb"],
            "max_total_storage_bytes": max_total_bytes,
            "max_file_count": max_count,
        },
        "usage": {
            "file_count": usage["file_count"],
            "total_bytes": usage["total_bytes"],
            "total_mb": round(usage["total_bytes"] / _MB, 2),
        },
        "remaining": {
            "files": remaining_files,
            "bytes": remaining_bytes,
            "mb": round(remaining_bytes / _MB, 2),
        },
        "percent_files": min(100.0, percent_files),
        "percent_storage": min(100.0, percent_storage),
        "exhausted": remaining_files <= 0 or remaining_bytes <= 0,
    }
