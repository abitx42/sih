"""
app/api/routes_reference.py
============================
Trusted-Reference Image Comparison API.

Endpoints:
  POST /api/evidence/{evidence_id}/reference-compare
      Upload a reference image and compare against the evidence exhibit.
      Returns comparison result including status, SSIM, and change regions.

  GET  /api/evidence/{evidence_id}/reference-compare
      Fetch the latest reference comparison result for an exhibit.

  GET  /api/evidence/{evidence_id}/forensic-artifact/reference_diff
      Serve the difference map PNG artifact.
"""
import uuid
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from app.config import EVIDENCE_DIR, FORENSIC_DIR, settings
from app.database import get_db
from app.core.reference_comparator import ReferenceComparator, STATUS_CONFIRMED, STATUS_INCONCLUSIVE
from app.core.chain_of_custody import ChainOfCustodyLogger
from app.security.validator import sanitize_filename, detect_mime_and_modality

logger = logging.getLogger(__name__)
router = APIRouter()

# Secure scratch directory for reference image files (not main evidence store)
REFERENCE_DIR = EVIDENCE_DIR.parent / "references"
REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_REFERENCE_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"
}


@router.post("/api/evidence/{evidence_id}/reference-compare")
async def submit_reference_comparison(
    evidence_id: str,
    reference_original: UploadFile = File(...),
    submitted_by: str = Form(default="Investigator"),
):
    """
    Upload a reference image and compare it against the evidence exhibit.

    The reference is stored securely in the references/ directory (not as a main
    evidence item). A custody event is recorded regardless of comparison outcome.

    Returns the comparison result. Status is either:
      REFERENCE_DIFFERENCE_CONFIRMED   — alignment succeeded and differences detected
      REFERENCE_COMPARISON_INCONCLUSIVE — alignment failed or no significant differences
    """
    # ── Validate evidence exists and is completed ──────────────────────────
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        ev = cursor.fetchone()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence item not found.")
    if ev.get("modality") != "IMAGE":
        raise HTTPException(status_code=400, detail="Reference comparison is only available for IMAGE exhibits.")
    if ev.get("status") not in ("COMPLETED", "FAILED"):
        raise HTTPException(status_code=400, detail="Evidence analysis must be complete before reference comparison.")

    # ── Validate reference file ────────────────────────────────────────────
    content = await reference_original.read()
    if len(content) > settings.REFERENCE_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Reference image exceeds maximum allowed size "
                   f"({settings.REFERENCE_MAX_SIZE_MB} MB)."
        )
    if len(content) < 512:
        raise HTTPException(status_code=400, detail="Reference image file is too small or empty.")

    # ── Save reference file securely ───────────────────────────────────────
    ref_filename = sanitize_filename(reference_original.filename or "reference.jpg")
    comparison_id = f"REF-{uuid.uuid4().hex[:8].upper()}"
    ext = Path(ref_filename).suffix or ".jpg"
    stored_ref_name = f"{comparison_id}{ext}"
    ref_path = REFERENCE_DIR / stored_ref_name
    ref_path.write_bytes(content)

    # MIME check via magic bytes
    try:
        mime_type, modality = detect_mime_and_modality(ref_path, ref_filename)
    except Exception:
        if ref_path.exists():
            ref_path.unlink()
        raise HTTPException(status_code=400, detail="Could not determine reference file type.")

    if mime_type not in ALLOWED_REFERENCE_MIMES or modality != "IMAGE":
        if ref_path.exists():
            ref_path.unlink()
        raise HTTPException(
            status_code=400,
            detail=f"Reference file must be an image (JPEG, PNG, WebP, BMP, TIFF). "
                   f"Detected MIME: {mime_type}."
        )

    # ── Run comparison ─────────────────────────────────────────────────────

    evidence_path = EVIDENCE_DIR / ev["stored_filename"]
    result = ReferenceComparator.compare(
        evidence_path=evidence_path,
        reference_path=ref_path,
        evidence_id=evidence_id,
        submitted_by=submitted_by,
    )

    submitted_at = datetime.utcnow().isoformat() + "Z"

    # ── Persist comparison result ──────────────────────────────────────────
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

    # ── Record custody event ───────────────────────────────────────────────
    action_label = (
        "REFERENCE_DIFFERENCE_CONFIRMED"
        if result["comparison_status"] == STATUS_CONFIRMED
        else "REFERENCE_COMPARISON_INCONCLUSIVE"
    )
    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="REFERENCE_COMPARISON_SUBMITTED",
        actor=submitted_by,
        recorded_sha256=ev["sha256_hash"],
        details=(
            f"Investigator-supplied comparison reference '{ref_filename}' (SHA-256: {result.get('reference_sha256', 'N/A')[:16]}...) "
            f"compared against exhibit. Outcome: {action_label}. "
            f"SSIM={result.get('ssim_score', 0):.3f}. "
            f"Changed regions: {result.get('changed_region_count', 0)}. "
            f"This comparison does not establish which editing tool or method caused the difference."
        ),
    )


    return {
        "comparison_id": comparison_id,
        "evidence_id": evidence_id,
        **result,
        "submitted_at": submitted_at,
        "submitted_by": submitted_by,
    }


@router.get("/api/evidence/{evidence_id}/reference-compare")
def get_reference_comparison(evidence_id: str):
    """Fetch the latest reference comparison result for an exhibit."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Check reference_comparisons table exists
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
