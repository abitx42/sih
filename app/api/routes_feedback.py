"""
app/api/routes_feedback.py
==========================
User Feedback, Bug Reporting, Accuracy Observations & Error Submission API.
Supports multipart/form-data with file attachments and JSON payloads.
"""
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel

from app.config import STORAGE_DIR
from app.database import get_db
from app.security.validator import sanitize_filename

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["Feedback & Bug Reports"])

FEEDBACK_ATTACHMENTS_DIR = STORAGE_DIR / "feedback_attachments"
FEEDBACK_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


class FeedbackJSONRequest(BaseModel):
    name: Optional[str] = "Anonymous Investigator"
    email: Optional[str] = None
    is_anonymous: bool = False
    category: str = "GENERAL_FEEDBACK"
    description: str
    evidence_id: Optional[str] = None
    rating: int = 5


@router.post("")
async def submit_feedback(request: Request):
    """
    Universal feedback submission endpoint.
    Accepts application/json, application/x-www-form-urlencoded, and multipart/form-data with attachments.
    """
    content_type = request.headers.get("content-type", "")

    name = "Anonymous Investigator"
    email = None
    is_anonymous = False
    category = "GENERAL_FEEDBACK"
    description = ""
    evidence_id = None
    rating = 5
    attachment_path_str = None

    if "application/json" in content_type:
        try:
            body = await request.json()
            name = body.get("name", "Anonymous Investigator")
            email = body.get("email")
            is_anonymous = bool(body.get("is_anonymous", False))
            category = body.get("category", "GENERAL_FEEDBACK")
            description = str(body.get("description", ""))
            evidence_id = body.get("evidence_id")
            rating = int(body.get("rating", 5))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")
    else:
        # Form or multipart/form-data
        try:
            form = await request.form()
            name = str(form.get("name", "Anonymous Investigator"))
            email = form.get("email")
            if email:
                email = str(email)
            raw_anon = form.get("is_anonymous", "false")
            is_anonymous = str(raw_anon).lower() in ("true", "1", "yes", "on")
            category = str(form.get("category", "GENERAL_FEEDBACK"))
            description = str(form.get("description", ""))
            evidence_id = form.get("evidence_id")
            if evidence_id:
                evidence_id = str(evidence_id)
            raw_rating = form.get("rating", 5)
            try:
                rating = int(raw_rating)
            except Exception:
                rating = 5

            attachment = form.get("attachment")
            if attachment and hasattr(attachment, "read") and getattr(attachment, "filename", None):
                content = await attachment.read()
                if len(content) > 15 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Feedback attachment must be under 15 MB.")
                clean_name = sanitize_filename(attachment.filename)
                ext = Path(clean_name).suffix.lower()
                allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".txt", ".log", ".json"}
                if ext not in allowed_exts:
                    raise HTTPException(status_code=400, detail="Invalid attachment format. Allowed: Images, PDF, TXT, LOG, JSON.")
                
                feedback_tmp_id = f"FBK-{uuid.uuid4().hex[:8].upper()}"
                saved_name = f"{feedback_tmp_id}{ext}"
                target_path = FEEDBACK_ATTACHMENTS_DIR / saved_name
                validate_safe_path(target_path, FEEDBACK_ATTACHMENTS_DIR)
                target_path.write_bytes(content)
                attachment_path_str = str(target_path)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid form payload: {e}")

    desc = description.strip()
    if not desc or len(desc) < 3:
        raise HTTPException(status_code=400, detail="Description must be at least 3 characters.")

    feedback_id = f"FBK-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.utcnow().isoformat() + "Z"

    final_name = "Anonymous" if is_anonymous else (name or "Anonymous Investigator")
    final_email = None if is_anonymous else email

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback (
                feedback_id, name, email, is_anonymous, category,
                description, evidence_id, rating, attachment_path, created_at, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            feedback_id, final_name, final_email, 1 if is_anonymous else 0,
            category.upper(), desc, evidence_id, max(1, min(5, rating)),
            attachment_path_str, now, now
        ))

    logger.info(f"Feedback submitted: {feedback_id} [{category}] by {final_name}")

    return {
        "success": True,
        "feedback_id": feedback_id,
        "message": "Thank you! Your feedback has been recorded.",
        "submitted_at": now
    }


@router.get("")
def list_feedback(limit: int = 100, offset: int = 0):
    """List submitted feedback for platform audit with pagination."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
        if not cursor.fetchone():
            return {"total": 0, "items": []}
        cursor.execute("SELECT COUNT(*) as cnt FROM feedback")
        total_row = cursor.fetchone()
        total = total_row["cnt"] if isinstance(total_row, dict) else (total_row[0] if total_row else 0)
        cursor.execute("SELECT * FROM feedback ORDER BY created_at DESC, submitted_at DESC LIMIT ? OFFSET ?", (max(1, min(500, limit)), max(0, offset)))
        rows = cursor.fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
