"""
Evidence Diff API Routes
POST /api/diff — compare two IMAGE evidence items
GET  /api/diff/{evidence_id_a}/{evidence_id_b}/heatmap — serve diff heatmap image
"""
import json
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import FORENSIC_DIR
from app.database import get_db
from app.core.evidence_diff import EvidenceDiffEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/diff", tags=["Evidence Diff"])


class EvidenceDiffRequest(BaseModel):
    evidence_id_a: str
    evidence_id_b: str


@router.post("")
def compare_evidence(req: EvidenceDiffRequest):
    """
    Compare two evidence items. Both must be IMAGE modality for pixel-level diff.
    Returns multi-signal diff including pixel heatmap, metadata diff, noise delta,
    and detected change regions.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (req.evidence_id_a,))
        ev_a = cursor.fetchone()
        if not ev_a:
            raise HTTPException(status_code=404, detail=f"Evidence '{req.evidence_id_a}' not found.")

        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (req.evidence_id_b,))
        ev_b = cursor.fetchone()
        if not ev_b:
            raise HTTPException(status_code=404, detail=f"Evidence '{req.evidence_id_b}' not found.")

        if ev_a.get("modality") != "IMAGE" or ev_b.get("modality") != "IMAGE":
            raise HTTPException(
                status_code=400,
                detail=f"Visual diff comparison requires both exhibits to be IMAGE modality. Found: '{ev_a.get('modality')}' and '{ev_b.get('modality')}'."
            )

        if ev_a["status"] not in ("COMPLETED",) or ev_b["status"] not in ("COMPLETED",):
            raise HTTPException(
                status_code=400,
                detail="Both evidence items must have completed forensic analysis before comparison."
            )

        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (req.evidence_id_a,))
        fr_a = cursor.fetchone()
        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (req.evidence_id_b,))
        fr_b = cursor.fetchone()

    from app.config import EVIDENCE_DIR
    file_a = EVIDENCE_DIR / ev_a["stored_filename"]
    file_b = EVIDENCE_DIR / ev_b["stored_filename"]

    if not file_a.exists():
        raise HTTPException(status_code=404, detail=f"Evidence file for '{req.evidence_id_a}' not found on disk.")
    if not file_b.exists():
        raise HTTPException(status_code=404, detail=f"Evidence file for '{req.evidence_id_b}' not found on disk.")

    result = EvidenceDiffEngine.compare(
        evidence_id_a=req.evidence_id_a,
        evidence_id_b=req.evidence_id_b,
        file_path_a=file_a,
        file_path_b=file_b,
        evidence_a=dict(ev_a),
        evidence_b=dict(ev_b),
        forensic_result_a=dict(fr_a) if fr_a else None,
        forensic_result_b=dict(fr_b) if fr_b else None,
        forensic_dir=FORENSIC_DIR
    )

    return result


@router.get("/{evidence_id_a}/{evidence_id_b}/heatmap")
def get_diff_heatmap(evidence_id_a: str, evidence_id_b: str):
    """Serve the pre-computed diff heatmap PNG image."""
    from app.core.security_guard import validate_safe_path
    heatmap_path = FORENSIC_DIR / f"diff_{evidence_id_a}_{evidence_id_b}.png"
    if not validate_safe_path(heatmap_path, FORENSIC_DIR):
        raise HTTPException(status_code=400, detail="Invalid exhibit identifiers.")
    if not heatmap_path.exists():
        raise HTTPException(status_code=404, detail="Diff heatmap not available. Run a comparison first.")
    return FileResponse(path=str(heatmap_path), media_type="image/png")
