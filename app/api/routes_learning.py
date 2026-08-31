"""
app/api/routes_learning.py
==========================
Self-Learning Feedback Loop & Active Learning Queue Endpoints (Phase 4).
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from app.core.self_learning import SelfLearningEngine
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/learning", tags=["Self-Learning Feedback Loop"])


class ConfirmLabelRequest(BaseModel):
    evidence_id: str
    confirmed_label: str  # AI_GENERATED | AUTHENTIC_REAL
    reviewer_name: str = "Lead Forensic Examiner"


@router.get("/stats")
def get_learning_stats():
    """Fetch self-learning dataset stats, class breakdown, and readiness percentage."""
    return SelfLearningEngine.get_dataset_statistics()


@router.get("/queue")
def get_active_learning_queue(limit: int = Query(20, ge=1, le=100)):
    """Fetch uncertain exhibits (0.35 - 0.65 confidence) for human verification."""
    return {
        "queue_count": len(SelfLearningEngine.get_active_learning_queue(limit=limit)),
        "items": SelfLearningEngine.get_active_learning_queue(limit=limit)
    }


@router.post("/confirm-label")
def confirm_ground_truth_label(body: ConfirmLabelRequest):
    """
    Directly assign or confirm verified ground-truth label for an evidence exhibit.
    """
    label = body.confirmed_label.upper().strip()
    if label not in ("AI_GENERATED", "AUTHENTIC_REAL"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid confirmed_label '{body.confirmed_label}'. Must be 'AI_GENERATED' or 'AUTHENTIC_REAL'."
        )

    res = SelfLearningEngine.record_review_feedback(
        evidence_id=body.evidence_id,
        verdict="CONFIRMED_GROUND_TRUTH",
        reviewer_name=body.reviewer_name,
        explicit_label=label
    )

    if not res:
        raise HTTPException(status_code=404, detail="Evidence exhibit or forensic result not found.")

    return {
        "success": True,
        "message": f"Ground-truth label '{label}' cataloged into self-learning dataset.",
        "sample": res,
        "stats": SelfLearningEngine.get_dataset_statistics()
    }


@router.get("/export-manifest")
def export_training_manifest():
    """Export complete training manifest for LoRA fine-tuning."""
    return SelfLearningEngine.export_training_manifest()


class QuickReviewRequest(BaseModel):
    examiner_verdict: Optional[str] = "CONFIRMED_AUTHENTIC_REAL"
    confirmed_label: Optional[str] = None
    notes: Optional[str] = ""
    submitted_by: Optional[str] = "Lead Examiner"


@router.post("/review/{evidence_id}")
def submit_quick_learning_review(evidence_id: str, body: QuickReviewRequest):
    raw_label = body.confirmed_label or body.examiner_verdict or "AUTHENTIC_REAL"
    label = "AI_GENERATED" if "AI" in raw_label.upper() or "FAKE" in raw_label.upper() else "AUTHENTIC_REAL"
    res = SelfLearningEngine.record_review_feedback(
        evidence_id=evidence_id,
        verdict="CONFIRMED_GROUND_TRUTH",
        reviewer_name=body.submitted_by or "Lead Examiner",
        explicit_label=label
    )
    if not res:
        raise HTTPException(status_code=404, detail="Evidence exhibit or forensic result not found.")
    return {
        "success": True,
        "message": "Review recorded in training dataset.",
        "evidence_id": evidence_id,
        "sample": res,
        "stats": SelfLearningEngine.get_dataset_statistics()
    }
