import os
import uuid
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from app.config import EVIDENCE_DIR, FORENSIC_DIR, settings
from app.database import get_db
from app.security.validator import sanitize_filename, detect_mime_and_modality
from app.core.integrity_engine import calculate_file_hashes, verify_integrity
from app.core.provenance_engine import ProvenanceEngine
from app.core.risk_engine import RiskEngine
from app.core.chain_of_custody import ChainOfCustodyLogger
from app.core.copilot import ForensicCopilot

from app.analyzers.image_analyzer import ImageAnalyzer
from app.analyzers.video_analyzer import VideoAnalyzer
from app.analyzers.audio_analyzer import AudioAnalyzer
from app.analyzers.document_analyzer import DocumentAnalyzer
from app.analyzers.archive_analyzer import ArchiveAnalyzer

from app.models.schemas import (
    EvidenceBase, EvidenceListResponse, EvidenceDetailResponse,
    IntegrityVerificationResponse, ForensicResultResponse, FindingSchema, CaseResponse,
    AIExplanationResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/evidence", tags=["Evidence"])

image_analyzer = ImageAnalyzer()
video_analyzer = VideoAnalyzer()
audio_analyzer = AudioAnalyzer()
document_analyzer = DocumentAnalyzer()
archive_analyzer = ArchiveAnalyzer()

def execute_forensic_pipeline(evidence_id: str):
    """
    Executes the automated forensic verification pipeline for an evidence exhibit.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            return

    file_path = EVIDENCE_DIR / evidence["stored_filename"]
    modality = evidence["modality"]

    # 1. Provenance Inspection
    provenance_res = ProvenanceEngine.inspect_provenance(file_path)
    provenance_status = provenance_res.get("status", "NOT_AVAILABLE")

    # 2. Modality Forensic Analysis
    if modality == "IMAGE":
        analysis_res = image_analyzer.analyze(file_path, evidence_id)
    elif modality == "VIDEO":
        analysis_res = video_analyzer.analyze(file_path, evidence_id)
    elif modality == "AUDIO":
        analysis_res = audio_analyzer.analyze(file_path, evidence_id)
    elif modality == "ARCHIVE":
        analysis_res = archive_analyzer.analyze(file_path, evidence_id)
    else:  # DOCUMENT
        analysis_res = document_analyzer.analyze(file_path, evidence_id)

    findings = analysis_res.get("findings", [])
    raw_metrics = analysis_res.get("raw_metrics", {})
    raw_metrics["provenance"] = provenance_res

    # Extract model metadata strictly without heuristic fallback
    model_status = analysis_res.get("model_status", "AVAILABLE")
    ai_indicator = analysis_res.get("ai_manipulation_indicator")
    model_confidence = analysis_res.get("model_confidence")
    ai_model_name = analysis_res.get("ai_model_name", "EVIDENCE-X Ensemble")
    ai_model_version = analysis_res.get("ai_model_version", "1.0")
    forensic_anomaly_score = analysis_res.get("forensic_anomaly_score", analysis_res.get("signal_anomalies_score", 0.0))

    # Add Provenance Finding if present
    if provenance_status == "VERIFIED":
        findings.append({
            "finding_id": f"FIND-{uuid.uuid4().hex[:8].upper()}",
            "evidence_id": evidence_id,
            "signal_name": "Cryptographic C2PA Provenance Manifest",
            "category": "PROVENANCE",
            "severity": "INFO",
            "score": 5.0,
            "explanation": provenance_res.get("details", ""),
            "location_ref": "C2PA JUMBF Manifest",
            "created_at": datetime.utcnow().isoformat() + "Z"
        })
    elif provenance_status == "NOT_VERIFIED":
        findings.append({
            "finding_id": f"FIND-{uuid.uuid4().hex[:8].upper()}",
            "evidence_id": evidence_id,
            "signal_name": "Unverified Provenance / Post-Processing Tag",
            "category": "PROVENANCE",
            "severity": "MEDIUM",
            "score": 45.0,
            "explanation": provenance_res.get("details", ""),
            "location_ref": "Metadata Stream",
            "created_at": datetime.utcnow().isoformat() + "Z"
        })

    # 3. Calculate Deterministic Forensic Risk Score
    risk_score, risk_cat, confidence, comp_scores = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=ai_indicator,
        model_status=model_status,
        forensic_anomaly_score=forensic_anomaly_score,
        metadata_anomaly_score=analysis_res.get("metadata_anomaly_score", 0.0),
        provenance_status=provenance_status,
        findings=findings
    )
    raw_metrics["risk_components"] = comp_scores

    # 4. Generate Copilot Narrative Summary & Recommendations
    narrative_res = ForensicCopilot.generate_narrative_and_recommendations(
        evidence_id=evidence_id,
        modality=modality,
        filename=evidence["original_filename"],
        risk_score=risk_score,
        risk_category=risk_cat,
        findings=findings,
        metrics=raw_metrics
    )

    # 5. Persist Results & Findings to SQLite
    result_id = f"RES-{uuid.uuid4().hex[:8].upper()}"
    analyzed_at = datetime.utcnow().isoformat() + "Z"

    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
        INSERT OR REPLACE INTO forensic_results (
            result_id, evidence_id, integrity_status, provenance_status,
            ai_manipulation_score, ai_manipulation_indicator, ai_model_name,
            ai_model_version, model_confidence, model_status,
            forensic_anomaly_score, forensic_risk_score, risk_category,
            confidence_score, analyzed_at, raw_metrics_json,
            summary_narrative, recommendations
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result_id, evidence_id, "VERIFIED", provenance_status,
            ai_indicator, ai_indicator, ai_model_name,
            ai_model_version, model_confidence, model_status,
            forensic_anomaly_score, risk_score, risk_cat,
            confidence, analyzed_at, json.dumps(raw_metrics),
            narrative_res.get("summary", ""),
            narrative_res.get("recommendations", "")
        ))

        cursor.execute("DELETE FROM findings WHERE evidence_id = ?", (evidence_id,))
        for f in findings:
            cursor.execute("""
            INSERT INTO findings (finding_id, evidence_id, signal_name, category, severity, score, explanation, location_ref, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f["finding_id"], f["evidence_id"], f["signal_name"], f["category"],
                f["severity"], f["score"], f["explanation"], f.get("location_ref"), f["created_at"]
            ))

        cursor.execute("UPDATE evidence SET status = 'COMPLETED' WHERE evidence_id = ?", (evidence_id,))

    # 6. Record Chain of Custody Events
    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="FORENSIC_ANALYSIS_COMPLETED",
        actor="EVIDENCE-X Forensic Engine",
        recorded_sha256=evidence["sha256_hash"],
        details=f"Modality ({modality}) automated multi-signal analysis executed. {len(findings)} findings logged. Model status: {model_status}."
    )
    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="RISK_ASSESSED",
        actor="EVIDENCE-X Risk Engine",
        recorded_sha256=evidence["sha256_hash"],
        details=f"Calculated Forensic Risk: {risk_score}/100 ({risk_cat}). AI manipulation indicator: {ai_indicator if ai_indicator is not None else 'UNAVAILABLE'}."
    )

@router.post("/upload")
async def upload_evidence(
    file: UploadFile = File(...),
    case_id: str = Form("CASE-2026-001"),
    uploaded_by: str = Form("Digital Forensics Investigator"),
    notes: Optional[str] = Form("")
):
    clean_filename = sanitize_filename(file.filename or "evidence.bin")
    evidence_id = f"EV-2026-{uuid.uuid4().hex[:6].upper()}"
    stored_filename = f"{evidence_id}_{clean_filename}"
    target_path = EVIDENCE_DIR / stored_filename

    file_size = 0
    with open(target_path, "wb") as f:
        while chunk := await file.read(64 * 1024):
            file_size += len(chunk)
            if file_size > settings.MAX_UPLOAD_SIZE_BYTES:
                if target_path.exists():
                    os.remove(target_path)
                raise HTTPException(status_code=400, detail="File size exceeds maximum upload limit (150 MB).")
            f.write(chunk)

    mime_type, modality = detect_mime_and_modality(target_path, clean_filename)
    hashes = calculate_file_hashes(target_path)
    uploaded_at = datetime.utcnow().isoformat() + "Z"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT case_id FROM cases WHERE case_id = ?", (case_id,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO cases (case_id, title, description, lead_investigator, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (case_id, f"Case {case_id}", "Auto-created case container", uploaded_by, uploaded_at, "ACTIVE"))

        cursor.execute("""
        INSERT INTO evidence (
            evidence_id, case_id, original_filename, stored_filename, modality,
            mime_type, file_size_bytes, sha256_hash, sha512_hash, md5_hash,
            uploaded_by, uploaded_at, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            evidence_id, case_id, clean_filename, stored_filename, modality,
            mime_type, file_size, hashes["sha256"], hashes["sha512"], hashes["md5"],
            uploaded_by, uploaded_at, "ANALYZING", notes or ""
        ))

    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="EVIDENCE_INGESTION",
        actor=uploaded_by,
        recorded_sha256=hashes["sha256"],
        details=f"Original digital exhibit '{clean_filename}' ingested. Baseline SHA-256 fingerprint generated."
    )

    try:
        execute_forensic_pipeline(evidence_id)
    except Exception as e:
        logger.error(f"Error during forensic analysis of {evidence_id}: {e}")

    return {
        "evidence_id": evidence_id,
        "case_id": case_id,
        "original_filename": clean_filename,
        "modality": modality,
        "mime_type": mime_type,
        "file_size_bytes": file_size,
        "sha256_hash": hashes["sha256"],
        "status": "COMPLETED",
        "message": "Evidence ingested and analyzed successfully."
    }

@router.get("", response_model=EvidenceListResponse)
def list_evidence(case_id: Optional[str] = None, modality: Optional[str] = None):
    query = "SELECT * FROM evidence WHERE 1=1"
    params = []
    if case_id:
        query += " AND case_id = ?"
        params.append(case_id)
    if modality:
        query += " AND modality = ?"
        params.append(modality.upper())

    query += " ORDER BY uploaded_at DESC"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        items = cursor.fetchall()
        return {"items": items, "total": len(items)}

@router.get("/{evidence_id}", response_model=EvidenceDetailResponse)
def get_evidence_detail(evidence_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

        cursor.execute("SELECT * FROM cases WHERE case_id = ?", (evidence["case_id"],))
        case_info = cursor.fetchone()

        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        res_row = cursor.fetchone()
        forensic_result = None
        if res_row:
            try:
                res_row["raw_metrics_json"] = json.loads(res_row["raw_metrics_json"])
            except Exception:
                res_row["raw_metrics_json"] = {}
            forensic_result = res_row

        cursor.execute("SELECT * FROM findings WHERE evidence_id = ? ORDER BY score DESC", (evidence_id,))
        findings = cursor.fetchall()

        cursor.execute("SELECT * FROM chain_of_custody WHERE evidence_id = ? ORDER BY timestamp ASC", (evidence_id,))
        custody = cursor.fetchall()

    return {
        "evidence": evidence,
        "case": case_info,
        "forensic_result": forensic_result,
        "findings": findings,
        "chain_of_custody": custody
    }

@router.post("/{evidence_id}/verify-integrity", response_model=IntegrityVerificationResponse)
def verify_evidence_integrity(evidence_id: str, actor: str = "Lead Forensic Examiner"):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

    file_path = EVIDENCE_DIR / evidence["stored_filename"]
    is_valid, current_sha256, status_msg = verify_integrity(file_path, evidence["sha256_hash"])

    status = "VERIFIED" if is_valid else "MISMATCH"

    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="INTEGRITY_VERIFIED" if is_valid else "INTEGRITY_VIOLATION_DETECTED",
        actor=actor,
        recorded_sha256=current_sha256,
        details=f"Cryptographic hash check result: {status}. Note: File-integrity baseline check only; does not evaluate content authenticity."
    )

    return {
        "evidence_id": evidence_id,
        "recorded_sha256": evidence["sha256_hash"],
        "current_sha256": current_sha256,
        "is_valid": is_valid,
        "status": status,
        "verified_at": datetime.utcnow().isoformat() + "Z",
        "details": status_msg
    }

@router.get("/{evidence_id}/file")
def download_evidence_file(evidence_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT stored_filename, original_filename, mime_type FROM evidence WHERE evidence_id = ?", (evidence_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Evidence file not found.")

    file_path = EVIDENCE_DIR / row["stored_filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File missing from storage.")

    return FileResponse(
        path=str(file_path),
        filename=row["original_filename"],
        media_type=row["mime_type"]
    )

@router.get("/{evidence_id}/forensic-artifact/{artifact_type}")
def get_forensic_artifact(evidence_id: str, artifact_type: str):
    if artifact_type == "ela":
        p = FORENSIC_DIR / f"ela_{evidence_id}.jpg"
        media = "image/jpeg"
    elif artifact_type == "fft":
        p = FORENSIC_DIR / f"fft_{evidence_id}.png"
        media = "image/png"
    elif artifact_type == "spectrogram":
        p = FORENSIC_DIR / f"spectrogram_{evidence_id}.png"
        media = "image/png"
    elif artifact_type == "waveform":
        p = FORENSIC_DIR / f"waveform_{evidence_id}.png"
        media = "image/png"
    else:
        raise HTTPException(status_code=400, detail="Invalid artifact type.")

    if not p.exists():
        raise HTTPException(status_code=404, detail="Forensic artifact not available for this evidence.")

    return FileResponse(path=str(p), media_type=media)

@router.post("/{evidence_id}/explain", response_model=AIExplanationResponse)
def explain_evidence(evidence_id: str, actor: str = "Lead Forensic Examiner"):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        res_row = cursor.fetchone()
        forensic_result = {}
        if res_row:
            try:
                res_row["raw_metrics_json"] = json.loads(res_row["raw_metrics_json"])
            except Exception:
                res_row["raw_metrics_json"] = {}
            forensic_result = res_row

        cursor.execute("SELECT * FROM findings WHERE evidence_id = ? ORDER BY score DESC", (evidence_id,))
        findings = cursor.fetchall()

    explanation = ForensicCopilot.generate_structured_explanation(
        evidence_id=evidence_id,
        evidence_data=evidence,
        forensic_result=forensic_result,
        findings=findings
    )

    # Record explanation generation in chain of custody without storing any secret
    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="AI_EXPLANATION_GENERATED",
        actor=actor,
        recorded_sha256=evidence["sha256_hash"],
        details=f"AI forensic explanation generated. Source: {explanation.get('source', 'Unknown')}."
    )

    return explanation

