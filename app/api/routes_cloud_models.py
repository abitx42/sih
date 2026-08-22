"""
app/api/routes_cloud_models.py
==============================
Zero-Cost Multi-Cloud Model Gateway & Cooldown Circuit Breaker API Endpoints.
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Path as FPath

from app.config import EVIDENCE_DIR
from app.core.cloud_vision_ensemble import MultiCloudVisionGateway
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cloud-models", tags=["Multi-Cloud Zero-Cost Model Gateway"])


@router.get("/status")
def get_cloud_providers_status():
    """Returns live health, cooldown timers, rate-limit status, and latency for all cloud providers."""
    providers = MultiCloudVisionGateway.get_providers_status()
    active_count = len([p for p in providers if p["is_ready"]])
    cooldown_count = len([p for p in providers if p["status"] == "COOLDOWN"])

    return {
        "total_providers": len(providers),
        "active_healthy_count": active_count,
        "cooldown_count": cooldown_count,
        "providers": providers
    }


@router.post("/cross-check/{evidence_id}")
def run_multi_cloud_cross_check(evidence_id: str = FPath(...)):
    """
    Executes a cross-check across all available zero-cost cloud vision models for an evidence exhibit.
    Combines results with automated rate-limit failover.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        ev = cursor.fetchone()
        if not ev:
            raise HTTPException(status_code=404, detail="Evidence exhibit not found.")

        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        fr = cursor.fetchone()

    img_path = EVIDENCE_DIR / ev["stored_filename"]
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Evidence image file missing.")

    ctx = {
        "evidence_id": evidence_id,
        "ai_indicator": fr.get("ai_manipulation_indicator") if fr else 0.5,
        "forensic_risk_score": fr.get("forensic_risk_score") if fr else 50.0,
        "risk_category": fr.get("risk_category") if fr else "UNKNOWN"
    }

    result = MultiCloudVisionGateway.analyze_image_multi_cloud(img_path, ctx)
    return {
        "success": True,
        "evidence_id": evidence_id,
        "filename": ev["original_filename"],
        "cross_check": result
    }
