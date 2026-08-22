"""
app/api/routes_feedback.py
==========================
User Feedback, Bug Reporting, Accuracy Observations & Error Submission API.
"""
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.config import STORAGE_DIR
from app.database import get_db
from app.security.validator import sanitize_filename

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["Feedback & Bug Reports"])

FEEDBACK_ATTACHMENTS_DIR = STORAGE_DIR / "feedback_attachments"
FEEDBACK_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


@router.post("")
async def submit_feedback(
    name: Optional[str] = Form(default="Anonymous Investigator"),
    email: Optional[str] = Form(default=None),
    is_anonymous: bool = Form(default=False),
    category: str = Form(default="GENERAL_FEEDBACK"), # BUG_REPORT | ACCURACY_OBSERVATION | FEATURE_REQUEST | GENERAL_FEEDBACK
    description: str = Form(...),
    evidence_id: Optional[str] = Form(default=None),
    rating: int = Form(default=5),
    attachment: Optional[UploadFile] = File(default=None)
):
    """
    Submit user feedback, bug report, accuracy correction or screenshot attachment.
    Supports anonymous submissions and file attachments.
    """
    desc = description.strip()
    if not desc or len(desc) < 5:
        raise HTTPException(status_code=400, detail="Description must be at least 5 characters.")

    feedback_id = f"FBK-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.utcnow().isoformat() + "Z"
    attachment_path_str = None

    if attachment and attachment.filename:
        try:
            content = await attachment.read()
            if len(content) > 15 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="Feedback attachment must be under 15 MB.")
            clean_name = sanitize_filename(attachment.filename)
            ext = Path(clean_name).suffix or ".jpg"
            saved_name = f"{feedback_id}{ext}"
            target_path = FEEDBACK_ATTACHMENTS_DIR / saved_name
            target_path.write_bytes(content)
            attachment_path_str = str(target_path)
        except Exception as e:
            logger.warning(f"Failed to save feedback attachment: {e}")

    final_name = "Anonymous" if is_anonymous else (name or "Anonymous Investigator")
    final_email = None if is_anonymous else email

    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                name TEXT,
                email TEXT,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                attachment_path TEXT,
                evidence_id TEXT,
                rating INTEGER DEFAULT 5,
                submitted_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO feedback (
                feedback_id, name, email, is_anonymous, category,
                description, attachment_path, evidence_id, rating, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            feedback_id, final_name, final_email, 1 if is_anonymous else 0,
            category, desc, attachment_path_str, evidence_id, rating, now
        ))

    logger.info(f"Feedback submitted: {feedback_id} [{category}] by {final_name}")

    return {
        "success": True,
        "feedback_id": feedback_id,
        "message": "Thank you for your feedback! Our forensic engineering team will review it.",
        "submitted_at": now
    }


@router.get("")
def list_feedback():
    """List all submitted feedback for platform audit."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
        if not cursor.fetchone():
            return {"total": 0, "items": []}
        cursor.execute("SELECT * FROM feedback ORDER BY submitted_at DESC")
        rows = cursor.fetchall()
        return {"total": len(rows), "items": [dict(r) for r in rows]}
