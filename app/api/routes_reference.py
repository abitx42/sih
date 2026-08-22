"""
app/api/routes_reference.py
============================
Trusted-Reference Image Comparison & Interactive Workspace API (Phase 3).
"""
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import EVIDENCE_DIR, FORENSIC_DIR, settings
from app.database import get_db
from app.core.reference_comparator import ReferenceComparator, STATUS_CONFIRMED, STATUS_INCONCLUSIVE
from app.core.chain_of_custody import ChainOfCustodyLogger
from app.security.validator import sanitize_filename, detect_mime_and_modality

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Reference Comparison Workspace"])

REFERENCE_DIR = EVIDENCE_DIR.parent / "references"
REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_REFERENCE_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"
}


class AutoCompareRequest(BaseModel):
    match_url: Optional[str] = None
    match_title: Optional[str] = None


@router.post("/api/evidence/{evidence_id}/reference-compare")
@router.post("/api/reference/compare/{evidence_id}")
async def submit_reference_comparison(
    evidence_id: str,
    reference_original: Optional[UploadFile] = File(default=None),
    reference_file: Optional[UploadFile] = File(default=None),
    file: Optional[UploadFile] = File(default=None),
    submitted_by: str = Form(default="Investigator"),
):
    """Upload a reference image and compare against the evidence exhibit."""
    upload = reference_original or reference_file or file
    if not upload:
        raise HTTPException(status_code=400, detail="Reference image file is required.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        ev = cursor.fetchone()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence item not found.")
    if ev.get("modality") != "IMAGE":
        raise HTTPException(status_code=400, detail="Reference comparison is only available for IMAGE exhibits.")

    content = await upload.read()
    if len(content) > settings.REFERENCE_MAX_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Reference image exceeds maximum allowed size.")
    if len(content) < 512:
        raise HTTPException(status_code=400, detail="Reference image file is too small or empty.")

    ref_filename = sanitize_filename((upload.filename if hasattr(upload, "filename") else None) or "reference.jpg")
    comparison_id = f"REF-{uuid.uuid4().hex[:8].upper()}"
    ext = Path(ref_filename).suffix or ".jpg"
    stored_ref_name = f"{comparison_id}{ext}"
    ref_path = REFERENCE_DIR / stored_ref_name
    ref_path.write_bytes(content)

    evidence_path = EVIDENCE_DIR / ev["stored_filename"]
    result = ReferenceComparator.compare(
        evidence_path=evidence_path,
        reference_path=ref_path,
        evidence_id=evidence_id,
        submitted_by=submitted_by,
        reference_title=ref_filename
    )

    submitted_at = datetime.utcnow().isoformat() + "Z"

    with get_db() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO reference_comparisons (
            comparison_id, evidence_id, reference_sha256, reference_filename,
            comparison_status, ssim_score, alignment_succeeded,
            difference_map_path, changed_region_count, submitted_at, submitted_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            comparison_id,
            evidence_id,
            result.get("reference_sha256", ""),
            ref_filename,
            result["comparison_status"],
            result.get("ssim_score"),
            1 if result.get("alignment_succeeded") else 0,
            result.get("difference_map_path"),
            result.get("changed_region_count", 0),
            submitted_at,
            submitted_by,
        ))

    action_label = "REFERENCE_DIFFERENCE_CONFIRMED" if result["comparison_status"] == STATUS_CONFIRMED else "REFERENCE_COMPARISON_INCONCLUSIVE"
    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="REFERENCE_COMPARISON_SUBMITTED",
        actor=submitted_by,
        recorded_sha256=ev["sha256_hash"],
        details=f"Reference comparison against '{ref_filename}'. Outcome: {action_label}. SSIM={result.get('ssim_score', 0):.3f}."
    )

    return {
        "comparison_id": comparison_id,
        "evidence_id": evidence_id,
        **result,
        "submitted_at": submitted_at,
        "submitted_by": submitted_by,
    }


@router.post("/api/evidence/{evidence_id}/auto-compare-web")
def auto_compare_web_source(
    evidence_id: str,
    body: AutoCompareRequest = Body(default=AutoCompareRequest())
):
    """
    Automated One-Click Reference Comparison against the identified web source (Phase 3).
    """
    try:
        res = ReferenceComparator.auto_compare_with_matched_source(
            evidence_id=evidence_id,
            match_url=body.match_url,
            match_title=body.match_title
        )

        submitted_at = datetime.utcnow().isoformat() + "Z"
        comparison_id = f"AUTOREF-{uuid.uuid4().hex[:8].upper()}"

        with get_db() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO reference_comparisons (
                comparison_id, evidence_id, reference_sha256, reference_filename,
                comparison_status, ssim_score, alignment_succeeded,
                difference_map_path, changed_region_count, submitted_at, submitted_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                comparison_id,
                evidence_id,
                res.get("reference_sha256", ""),
                body.match_title or "Matched Web Source",
                res["comparison_status"],
                res.get("ssim_score"),
                1 if res.get("alignment_succeeded") else 0,
                res.get("difference_map_path"),
                res.get("changed_region_count", 0),
                submitted_at,
                "Truth Lens Auto-Provenance Engine",
            ))

        return {
            "success": True,
            "comparison_id": comparison_id,
            "evidence_id": evidence_id,
            **res,
            "submitted_at": submitted_at
        }
    except Exception as e:
        logger.error(f"Auto-compare error for {evidence_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/evidence/{evidence_id}/reference-compare")
def get_reference_comparison(evidence_id: str):
    """Fetch the latest reference comparison result for an exhibit."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reference_comparisons'"
        )
        if not cursor.fetchone():
            return None
        cursor.execute(
            "SELECT * FROM reference_comparisons WHERE evidence_id = ? ORDER BY submitted_at DESC LIMIT 1",
            (evidence_id,)
        )
        row = cursor.fetchone()
    if not row:
        return None
    return dict(row)


@router.get("/api/evidence/{evidence_id}/forensic-artifact/reference_diff")
def get_reference_diff_artifact(evidence_id: str):
    """Serve the reference difference map PNG."""
    artifact_path = FORENSIC_DIR / f"reference_diff_{evidence_id}.png"
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Reference difference map not found.")
    return FileResponse(str(artifact_path), media_type="image/png")


@router.get("/api/evidence/{evidence_id}/forensic-artifact/reference_side_by_side")
def get_reference_side_by_side_artifact(evidence_id: str):
    """Serve the side-by-side composite comparison PNG (Phase 3)."""
    artifact_path = FORENSIC_DIR / f"reference_side_by_side_{evidence_id}.png"
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Side-by-side comparison composite not found.")
    return FileResponse(str(artifact_path), media_type="image/png")
