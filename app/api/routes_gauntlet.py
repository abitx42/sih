"""
app/api/routes_gauntlet.py
==========================
The Turing Gauntlet API Endpoints:
  - GET /api/gauntlet/challenge   : Fetch randomized forensic challenge item
  - GET /api/gauntlet/speed-batch : Fetch sequence of N challenges for rapid-fire 3-second gameplay
  - POST /api/gauntlet/submit     : Submit human guess, evaluate vs Truth Lens, feed active learning
  - GET /api/gauntlet/stats       : Human vs Truth Lens cumulative accuracy leaderboard
  - GET /api/gauntlet/sample/{filename} : Serve challenge exhibit image
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.turing_gauntlet import TuringGauntletEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/gauntlet", tags=["The Turing Gauntlet"])


class GauntletSubmissionRequest(BaseModel):
    challenge_id: str
    user_guess: str  # "REAL" | "AI"
    response_time_ms: Optional[int] = 0
    investigator_name: Optional[str] = "Lead Examiner"


@router.get("/challenge")
def get_gauntlet_challenge():
    """Returns a randomized blind forensic exhibit challenge for the investigator."""
    return TuringGauntletEngine.get_challenge()


@router.get("/speed-batch")
def get_gauntlet_speed_batch(count: int = Query(10, ge=3, le=20)):
    """Returns a rapid-fire batch of N unique challenges for the ingestion mini-game."""
    return {
        "count": count,
        "challenges": TuringGauntletEngine.get_speed_batch(count=count)
    }


@router.post("/submit")
def submit_gauntlet_guess(body: GauntletSubmissionRequest):
    """
    Evaluates human investigator verdict against ground truth & Truth Lens,
    returns detailed forensic artifact breakdown, and updates active learning dataset.
    """
    return TuringGauntletEngine.evaluate_submission(
        challenge_id=body.challenge_id,
        user_guess=body.user_guess,
        response_time_ms=body.response_time_ms or 0,
        investigator_name=body.investigator_name or "Investigator"
    )


@router.get("/stats")
def get_gauntlet_stats():
    """Returns overall Gauntlet accuracy benchmarks (Human vs Truth Lens AI)."""
    return TuringGauntletEngine.get_statistics()


@router.get("/sample/{filename}")
def get_gauntlet_sample_file(filename: str):
    """Serves high-resolution challenge image for the Gauntlet game."""
    path = TuringGauntletEngine.get_sample_image_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Challenge sample not found.")
    return FileResponse(path, media_type="image/jpeg")
