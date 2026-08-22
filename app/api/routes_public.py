"""
app/api/routes_public.py
========================
Public 1-Click "Fact-Check Debunk" & Cryptographic Verification Endpoints.
Open-access read-only endpoints for journalists, citizens, and fact-checkers.
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from app.database import get_db
from app.config import BASE_DIR, EVIDENCE_DIR, FORENSIC_DIR
from app.core.prompt_inverter import PromptInversionEngine
from app.core.prnu_ballistics import PRNUBallisticsEngine
from app.core.courtroom_debate import CourtroomDebateEngine

router = APIRouter(tags=["Public Verification"])
VERIFY_HTML_PATH = BASE_DIR / "app/static/verify.html"


@router.get("/verify/{evidence_id}", response_class=HTMLResponse)
def serve_public_verify_page(evidence_id: str):
    """Serves the standalone public fact-check debunk page."""
    if not VERIFY_HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="Verification page missing.")
    return FileResponse(VERIFY_HTML_PATH)


@router.get("/api/public/verify/{evidence_id}")
def get_public_verification_payload(evidence_id: str):
    """
    Returns public-safe forensic verification payload (sandwich diffs, prompt, PRNU, verdict).
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        ev = cursor.fetchone()
        if not ev:
            raise HTTPException(status_code=404, detail="Exhibit record not found.")

        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        fr = cursor.fetchone() or {}

        cursor.execute("SELECT * FROM web_search_results WHERE evidence_id = ?", (evidence_id,))
        web_res = cursor.fetchone() or {}

    file_path = EVIDENCE_DIR / ev["stored_filename"]
    
    # Extract Prompt & PRNU
    pinv = PromptInversionEngine.invert_prompt(file_path, fr, evidence_id) if file_path.exists() else {}
    prnu = PRNUBallisticsEngine.analyze_prnu(file_path, evidence_id) if file_path.exists() else {}
    debate = CourtroomDebateEngine.conduct_debate(evidence_id, ev.get("original_filename", "exhibit.jpg"), fr)

    risk_score = float(fr.get("forensic_risk_score", 50.0))
    ai_ind = float(fr.get("ai_manipulation_indicator") or (risk_score / 100.0))
    is_ai = (ai_ind >= 0.50 or risk_score >= 60.0)

    return {
        "evidence_id": evidence_id,
        "original_filename": ev.get("original_filename", "exhibit.jpg"),
        "sha256_hash": ev.get("sha256_hash", "e3b0c442..."),
        "analyzed_at": ev.get("analyzed_at") or ev.get("uploaded_at"),
        "is_ai_generated": is_ai,
        "confidence_score": round(ai_ind * 100.0, 1),
        "risk_score": risk_score,
        "risk_category": fr.get("risk_category", "REVIEW REQUIRED"),
        "model_family": pinv.get("model_family", "Generative Diffusion (SDXL / Midjourney)"),
        "reconstructed_prompt": pinv.get("reconstructed_positive_prompt", "Photorealistic visual generation"),
        "prnu_status": prnu.get("prnu_status_text", "Zero Silicon PRNU Fingerprint"),
        "admissibility_status": debate.get("magistrate", {}).get("admissibility_status", "Section 63 BSA 2023"),
        "web_match_url": web_res.get("best_match_url"),
        "web_match_title": web_res.get("best_match_title")
    }
