"""
Investigator Review API Routes
POST /api/reviews/{evidence_id}       — submit an investigator verdict
GET  /api/reviews/{evidence_id}       — fetch current review
"""
import uuid
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.core.chain_of_custody import ChainOfCustodyLogger

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reviews", tags=["Investigator Review"])

VALID_VERDICTS = {"AGREE", "DISAGREE", "NEEDS_FURTHER_EXAMINATION"}


class InvestigatorReviewRequest(BaseModel):
    verdict: str  # AGREE | DISAGREE | NEEDS_FURTHER_EXAMINATION
    notes: Optional[str] = None
    reviewer_name: str = "Lead Forensic Examiner"


class InvestigatorReviewResponse(BaseModel):
    review_id: str
    evidence_id: str
    verdict: str
    notes: Optional[str]
    reviewer_name: str
    submitted_at: str


@router.post("/{evidence_id}", response_model=InvestigatorReviewResponse)
def submit_review(evidence_id: str, req: InvestigatorReviewRequest):
    """
    Record a human investigator verdict on a completed forensic analysis.
    Verdict is logged to the chain of custody for auditability.
    """
    verdict = req.verdict.upper().replace(" ", "_")
    if verdict not in VALID_VERDICTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid verdict '{req.verdict}'. Must be one of: {', '.join(sorted(VALID_VERDICTS))}"
        )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT evidence_id, sha256_hash, status FROM evidence WHERE evidence_id = ?", (evidence_id,))
        ev = cursor.fetchone()
        if not ev:
            raise HTTPException(status_code=404, detail="Evidence not found.")
        if ev["status"] not in ("COMPLETED", "FAILED"):
            raise HTTPException(status_code=400, detail="Investigator review can only be submitted after forensic analysis is completed.")

    review_id = f"REV-{uuid.uuid4().hex[:10].upper()}"
    submitted_at = datetime.utcnow().isoformat() + "Z"
    notes = (req.notes or "").strip()

    with get_db() as conn:
        cursor = conn.cursor()
        # Upsert: replace any prior review for this evidence
        cursor.execute("DELETE FROM investigator_reviews WHERE evidence_id = ?", (evidence_id,))
        cursor.execute("""
        INSERT INTO investigator_reviews (review_id, evidence_id, verdict, notes, reviewer_name, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (review_id, evidence_id, verdict, notes or None, req.reviewer_name, submitted_at))

    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="INVESTIGATOR_REVIEW_SUBMITTED",
        actor=req.reviewer_name,
        recorded_sha256=ev["sha256_hash"],
        details=f"Investigator verdict: {verdict}. Notes: {notes or 'None provided'}."
    )

    return InvestigatorReviewResponse(
        review_id=review_id,
        evidence_id=evidence_id,
        verdict=verdict,
        notes=notes or None,
        reviewer_name=req.reviewer_name,
        submitted_at=submitted_at
    )


@router.get("/{evidence_id}", response_model=Optional[InvestigatorReviewResponse])
def get_review(evidence_id: str):
    """Fetch the current investigator review for an evidence item."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM investigator_reviews WHERE evidence_id = ? ORDER BY submitted_at DESC LIMIT 1", (evidence_id,))
        row = cursor.fetchone()

    if not row:
        return None

    return InvestigatorReviewResponse(
        review_id=row["review_id"],
        evidence_id=row["evidence_id"],
        verdict=row["verdict"],
        notes=row.get("notes"),
        reviewer_name=row["reviewer_name"],
        submitted_at=row["submitted_at"]
    )
