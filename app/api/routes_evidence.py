import os
import uuid
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
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
from app.core.explainability import ForensicCorrelationBuilder
from app.core.evidence_dna import EvidenceDNA
from app.core.confidence_matrix import ConfidenceMatrix
from app.core.robustness_tester import RobustnessTester
from app.core.reproducibility import ReproducibilityEngine
from app.core.localization_policy import PolicyEngine, OUTCOME_INCONCLUSIVE
from app.analyzers.localization_analyzer import LocalizationAnalyzer
from app.core.detector_ensemble import (
    SpatialVisionSpecialist, FrequencyDomainSpecialist, SyntheticNoiseSpecialist,
    LocalizedPatchSpecialist, ProvenanceMetadataSpecialist, EnsembleAgreementEngine,
    SIGNAL_ALTERATION_DETECTED, SIGNAL_NO_STRONG_ANOMALY, SIGNAL_INCONCLUSIVE
)

from app.analyzers.image_analyzer import ImageAnalyzer
from app.analyzers.video_analyzer import VideoAnalyzer
from app.analyzers.audio_analyzer import AudioAnalyzer
from app.analyzers.document_analyzer import DocumentAnalyzer
from app.analyzers.archive_analyzer import ArchiveAnalyzer

from app.models.schemas import (
    EvidenceBase, EvidenceListResponse, EvidenceDetailResponse,
    IntegrityVerificationRequest, IntegrityVerificationResponse, ForensicResultResponse, FindingSchema, CaseResponse,
    AIExplanationResponse, BulkUploadResponse, BulkUploadItemResponse, PipelineProgressResponse, EvidenceStatusResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/evidence", tags=["Evidence"])

image_analyzer = ImageAnalyzer()
video_analyzer = VideoAnalyzer()
audio_analyzer = AudioAnalyzer()
document_analyzer = DocumentAnalyzer()
archive_analyzer = ArchiveAnalyzer()
localization_analyzer = LocalizationAnalyzer()

spatial_specialist = SpatialVisionSpecialist()
frequency_specialist = FrequencyDomainSpecialist()
synthetic_noise_specialist = SyntheticNoiseSpecialist()
localized_patch_specialist = LocalizedPatchSpecialist()
provenance_metadata_specialist = ProvenanceMetadataSpecialist()


def _update_stage(evidence_id: str, stage_key: str, status: str, details: str, result_summary: Optional[Dict[str, Any]] = None):
    now_ts = datetime.utcnow().isoformat() + "Z"
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT pipeline_stages_json FROM evidence WHERE evidence_id = ?", (evidence_id,))
            row = cursor.fetchone()
            stages = {}
            if row and row.get("pipeline_stages_json"):
                try:
                    stages = json.loads(row["pipeline_stages_json"])
                except Exception:
                    pass
            stages[stage_key] = {
                "stage_key": stage_key,
                "status": status,
                "updated_at": now_ts,
                "details": details,
                "summary": result_summary
            }
            cursor.execute("UPDATE evidence SET pipeline_stages_json = ? WHERE evidence_id = ?", (json.dumps(stages), evidence_id))
    except Exception as err:
        logger.warning(f"Failed to update stage {stage_key} for {evidence_id}: {err}")

def execute_forensic_pipeline(evidence_id: str):
    """
    Executes the automated multi-specialist forensic verification pipeline for an evidence exhibit.
    Runs asynchronously via BackgroundTasks.
    """
    analysis_started_at = datetime.utcnow().isoformat() + "Z"
    with get_db() as conn:
        conn.execute("""
        UPDATE evidence 
        SET status = 'ANALYZING', pipeline_status = 'ANALYZING', analysis_started_at = ?
        WHERE evidence_id = ?
        """, (analysis_started_at, evidence_id))

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
            evidence = cursor.fetchone()
            if not evidence:
                return

        file_path = EVIDENCE_DIR / evidence["stored_filename"]
        modality = evidence["modality"]
        analysis_mode = evidence.get("analysis_mode", "FULL_ANALYSIS")

        # Stage 1: Cryptographic Integrity Baseline
        _update_stage(evidence_id, "INTEGRITY_BASELINE", "COMPLETED", f"SHA-256 baseline computed ({evidence['sha256_hash'][:16]}...)")

        # Stage 2: Metadata & Provenance Inspection
        _update_stage(evidence_id, "METADATA_PROVENANCE", "ANALYZING", "Inspecting container metadata & C2PA manifest...")
        provenance_res = ProvenanceEngine.inspect_provenance(file_path)
        provenance_status = provenance_res.get("status", "NOT_AVAILABLE")
        _update_stage(evidence_id, "METADATA_PROVENANCE", "COMPLETED", f"Provenance status: {provenance_status.replace('_', ' ')}")

        # Stage 3: Modality Forensic Pipeline Execution
        _update_stage(evidence_id, "AI_DETECTOR_ENSEMBLE", "ANALYZING", "Executing multi-specialist AI & frequency ensemble...")
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
        raw_metrics["analysis_mode"] = analysis_mode

        # Extract model metadata strictly without heuristic fallback
        model_status = analysis_res.get("model_status", "ANALYSIS_UNAVAILABLE")
        ai_indicator = analysis_res.get("ai_manipulation_indicator")
        model_confidence = analysis_res.get("model_confidence")
        ai_model_name = analysis_res.get("ai_model_name") or "Truth Lens Signal Engine"
        ai_model_version = analysis_res.get("ai_model_version") or "1.0"
        forensic_anomaly_score = float(analysis_res.get("forensic_anomaly_score", analysis_res.get("signal_anomalies_score", 0.0)))

        # Add Provenance Finding if present
        if provenance_status == "DETECTED_UNVERIFIED_MANIFEST" or "DETECTED" in provenance_status:
            findings.append({
                "finding_id": f"FIND-{uuid.uuid4().hex[:8].upper()}",
                "evidence_id": evidence_id,
                "signal_name": "C2PA Provenance Manifest Marker Detected (Unverified)",
                "category": "PROVENANCE",
                "severity": "INFO",
                "score": 25.0,
                "explanation": provenance_res.get("details", ""),
                "location_ref": "C2PA JUMBF Container Atom",
                "created_at": datetime.utcnow().isoformat() + "Z"
            })
        elif provenance_status == "NOT_VERIFIED":
            findings.append({
                "finding_id": f"FIND-{uuid.uuid4().hex[:8].upper()}",
                "evidence_id": evidence_id,
                "signal_name": "Post-Processing Editing Suite Tag Detected",
                "category": "PROVENANCE",
                "severity": "MEDIUM",
                "score": 45.0,
                "explanation": provenance_res.get("details", ""),
                "location_ref": "Metadata Stream",
                "created_at": datetime.utcnow().isoformat() + "Z"
            })

        # Stage 4: Pixel Forensics (ELA & High-Pass Noise)
        _update_stage(evidence_id, "PIXEL_FORENSICS", "COMPLETED", f"ELA 95% & Noise variance residual calculated ({forensic_anomaly_score:.1f}/100 anomaly)")

        # Stage 5: Localized Region Analysis (Patch localizer)
        localized_regions = raw_metrics.get("localized_regions", [])
        if localized_regions:
            _update_stage(evidence_id, "LOCAL_REGION_ANALYSIS", "COMPLETED", f"Localized ROI detected: {localized_regions[0].get('semantic_label', 'ROI')}")
        else:
            _update_stage(evidence_id, "LOCAL_REGION_ANALYSIS", "COMPLETED", "Uniform patch distribution across frame")

        # Stage 5b: Multi-Signal Localization Analysis (IMAGE only)
        localization_result = None
        if modality == "IMAGE":
            _update_stage(evidence_id, "LOCALIZATION_ANALYSIS", "ANALYZING", "Running multi-signal spatial localization (ELA grid, noise map, FFT block, patch heatmap)...")
            try:
                from PIL import Image as _PILImage
                _img_for_loc = _PILImage.open(file_path).convert("RGB")
                localization_result = localization_analyzer.analyze(file_path, evidence_id, img=_img_for_loc)
                loc_status = localization_result.get("localization_status", "UNAVAILABLE")
                n_regions = len(localization_result.get("localized_regions", []))
                raw_metrics["localization"] = localization_result
                _update_stage(
                    evidence_id, "LOCALIZATION_ANALYSIS", "COMPLETED",
                    f"Localization: {loc_status} — {n_regions} suspicious region(s) mapped."
                )
            except Exception as _loc_err:
                localization_result = None
                raw_metrics["localization"] = {"localization_status": "ERROR", "error_detail": str(type(_loc_err).__name__)}
                _update_stage(evidence_id, "LOCALIZATION_ANALYSIS", "COMPLETED", "Localization unavailable for this exhibit.")
        else:
            raw_metrics["localization"] = {"localization_status": "UNAVAILABLE", "error_detail": "Localization is only available for IMAGE exhibits."}

        # Stage 6: Build Specialist Ensemble & Agreement Engine
        _update_stage(evidence_id, "EVIDENCE_CORRELATION", "ANALYZING", "Evaluating multi-specialist consensus & agreement matrix...")
        specialists = []
        if modality == "IMAGE":
            vit_verdict = (
                SIGNAL_ALTERATION_DETECTED if (ai_indicator or 0) >= 0.65
                else (SIGNAL_NO_STRONG_ANOMALY if (ai_indicator or 0) <= 0.35 else SIGNAL_INCONCLUSIVE)
            )
            specialists.append({
                "name": "Spatial Vision Classifier (ViT)",
                "specialist_type": "SPATIAL_VISION",
                "category": "AI_MODEL",
                "status": "COMPLETED" if model_status == "AVAILABLE" else model_status,
                "verdict": vit_verdict,
                "indicator": ai_indicator,
                "evidence_strength": "HIGH" if (ai_indicator or 0) >= 0.85 else ("MODERATE" if (ai_indicator or 0) >= 0.65 else "LOW"),
                "calibration_status": "UNVALIDATED",
                "focus": "Global facial & spatial scene semantics",
                "details": f"ViT screening signal: {vit_verdict} (Statistical indicator: {ai_indicator if ai_indicator is not None else 'UNAVAILABLE'})"
            })
            specialists.append(frequency_specialist.analyze(None, float(raw_metrics.get("fft_anomaly_score", 0.0)), float(raw_metrics.get("checkerboard_score", 0.0))))
            specialists.append(synthetic_noise_specialist.analyze(None, float(raw_metrics.get("noise_anomaly_score", 0.0))))
            specialists.append(localized_patch_specialist.analyze({
                "max_patch_anomaly": raw_metrics.get("max_patch_anomaly", 0.0),
                "localized_regions": localized_regions
            }))
            specialists.append(provenance_metadata_specialist.analyze(provenance_res, raw_metrics.get("metadata", {})))
        else:
            mod_verdict = (
                SIGNAL_ALTERATION_DETECTED if forensic_anomaly_score >= 55.0
                else (SIGNAL_NO_STRONG_ANOMALY if forensic_anomaly_score <= 35.0 else SIGNAL_INCONCLUSIVE)
            )
            specialists.append({
                "name": f"{modality.capitalize()} Forensic Specialist",
                "specialist_type": f"{modality}_SPECIALIST",
                "category": "PHYSICAL_SIGNAL",
                "status": "COMPLETED",
                "verdict": mod_verdict,
                "indicator": forensic_anomaly_score / 100.0,
                "evidence_strength": "HIGH" if forensic_anomaly_score >= 75.0 else "MODERATE",
                "calibration_status": "UNVALIDATED",
                "focus": f"{modality.capitalize()} structural & acoustic integrity",
                "details": f"Forensic Anomaly Score: {forensic_anomaly_score:.1f}/100"
            })
            specialists.append(provenance_metadata_specialist.analyze(provenance_res, raw_metrics.get("metadata", {})))

        ensemble_agreement = EnsembleAgreementEngine.evaluate_consensus(specialists)
        raw_metrics["ensemble_agreement"] = ensemble_agreement


        # 8. Calculate Deterministic Forensic Risk Score & 5-Tier Taxonomy
        risk_score, risk_cat, confidence, comp_scores = RiskEngine.calculate_risk(
            integrity_status="VERIFIED",
            ai_manipulation_indicator=ai_indicator,
            model_status=model_status,
            forensic_anomaly_score=forensic_anomaly_score,
            metadata_anomaly_score=float(analysis_res.get("metadata_anomaly_score", 0.0)),
            provenance_status=provenance_status,
            findings=findings,
            ensemble_agreement=ensemble_agreement
        )
        raw_metrics["risk_components"] = comp_scores
        forensic_taxonomy = comp_scores.get("forensic_taxonomy", "ANALYSIS_INCONCLUSIVE")
        raw_metrics["forensic_taxonomy"] = forensic_taxonomy

        # 8b. Evaluate Evidence-Result Policy (transparent 6-tier outcome)
        policy_result = PolicyEngine.evaluate(
            provenance_status=provenance_status,
            reference_comparison=None,  # populated post-hoc if reference is submitted
            localization_result=localization_result,
            ai_manipulation_indicator=ai_indicator,
            model_status=model_status,
            findings=findings,
            ensemble_agreement=ensemble_agreement,
        )
        raw_metrics["policy_outcome"] = policy_result

        # 9. Generate Multi-Signal 'Why + Where + How' Correlation Matrix
        correlation_matrix = ForensicCorrelationBuilder.build_correlation(
            evidence_id=evidence_id,
            forensic_taxonomy=forensic_taxonomy,
            risk_category=risk_cat,
            risk_score=risk_score,
            findings=findings,
            metrics=raw_metrics
        )
        raw_metrics["correlation_summary"] = correlation_matrix

        # 10. Generate Copilot Narrative Summary & Recommendations
        narrative_res = ForensicCopilot.generate_narrative_and_recommendations(
            evidence_id=evidence_id,
            modality=modality,
            filename=evidence["original_filename"],
            risk_score=risk_score,
            risk_category=risk_cat,
            findings=findings,
            metrics=raw_metrics
        )

        _update_stage(evidence_id, "EVIDENCE_CORRELATION", "COMPLETED", f"Assessment complete: {forensic_taxonomy.replace('_', ' ')} ({risk_cat})")

        # 11. Persist Results & Findings to SQLite
        result_id = f"RES-{uuid.uuid4().hex[:8].upper()}"
        analyzed_at = datetime.utcnow().isoformat() + "Z"
        manipulation_subtype = comp_scores.get("manipulation_subtype", "INCONCLUSIVE")

        def _json_safe(obj):
            if hasattr(obj, "tolist"):
                return obj.tolist()
            if hasattr(obj, "__float__"):
                return float(obj)
            if hasattr(obj, "__int__"):
                return int(obj)
            return str(obj)

        # Build Evidence DNA fingerprint
        dna_record = EvidenceDNA.build_dna(
            evidence_id=evidence_id,
            sha256_hash=evidence["sha256_hash"],
            original_filename=evidence["original_filename"],
            modality=modality,
            file_size_bytes=evidence["file_size_bytes"],
            raw_metrics=raw_metrics,
            provenance_result=provenance_res
        )
        raw_metrics["evidence_dna"] = dna_record

        # Build reproducibility record
        reproducibility_record = ReproducibilityEngine.build_record(
            evidence_id=evidence_id,
            input_sha256=evidence["sha256_hash"],
            modality=modality,
            analysis_mode=analysis_mode,
            model_name=ai_model_name,
            model_version=ai_model_version,
            forensic_anomaly_score=forensic_anomaly_score,
            ensemble_specialist_count=len(specialists)
        )

        with get_db() as conn:
            cursor = conn.cursor()

            # Check columns available
            cursor.execute("PRAGMA table_info(forensic_results)")
            fr_cols = [c["name"] for c in cursor.fetchall()]
            has_manip_subtype = "manipulation_subtype" in fr_cols
            has_repro = "reproducibility_json" in fr_cols
            has_localization = "localization_status" in fr_cols and "localization_json" in fr_cols and "policy_outcome" in fr_cols

            localization_status_val = (
                localization_result.get("localization_status", "UNAVAILABLE")
                if localization_result else "UNAVAILABLE"
            )
            localization_json_val = json.dumps(
                localization_result if localization_result else {}, default=_json_safe
            )
            policy_outcome_val = policy_result.get("outcome", OUTCOME_INCONCLUSIVE)

            if has_manip_subtype and has_repro and has_localization:
                cursor.execute("""
                INSERT OR REPLACE INTO forensic_results (
                    result_id, evidence_id, integrity_status, provenance_status,
                    ai_manipulation_score, ai_manipulation_indicator, ai_model_name,
                    ai_model_version, model_confidence, model_status,
                    forensic_anomaly_score, forensic_risk_score, risk_category,
                    confidence_score, analyzed_at, raw_metrics_json,
                    summary_narrative, recommendations, ensemble_agreement_json,
                    manipulation_subtype, reproducibility_json,
                    localization_status, localization_json, policy_outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result_id, evidence_id, "VERIFIED", provenance_status,
                    ai_indicator if ai_indicator is not None else 0.0, ai_indicator, ai_model_name,
                    ai_model_version, model_confidence, model_status,
                    forensic_anomaly_score, risk_score, risk_cat,
                    confidence, analyzed_at, json.dumps(raw_metrics, default=_json_safe),
                    narrative_res.get("summary", ""),
                    narrative_res.get("recommendations", ""),
                    json.dumps(ensemble_agreement, default=_json_safe),
                    manipulation_subtype,
                    json.dumps(reproducibility_record, default=_json_safe),
                    localization_status_val,
                    localization_json_val,
                    policy_outcome_val,
                ))
            elif has_manip_subtype and has_repro:
                cursor.execute("""
                INSERT OR REPLACE INTO forensic_results (
                    result_id, evidence_id, integrity_status, provenance_status,
                    ai_manipulation_score, ai_manipulation_indicator, ai_model_name,
                    ai_model_version, model_confidence, model_status,
                    forensic_anomaly_score, forensic_risk_score, risk_category,
                    confidence_score, analyzed_at, raw_metrics_json,
                    summary_narrative, recommendations, ensemble_agreement_json,
                    manipulation_subtype, reproducibility_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result_id, evidence_id, "VERIFIED", provenance_status,
                    ai_indicator if ai_indicator is not None else 0.0, ai_indicator, ai_model_name,
                    ai_model_version, model_confidence, model_status,
                    forensic_anomaly_score, risk_score, risk_cat,
                    confidence, analyzed_at, json.dumps(raw_metrics, default=_json_safe),
                    narrative_res.get("summary", ""),
                    narrative_res.get("recommendations", ""),
                    json.dumps(ensemble_agreement, default=_json_safe),
                    manipulation_subtype,
                    json.dumps(reproducibility_record, default=_json_safe)
                ))

            else:
                cursor.execute("""
                INSERT OR REPLACE INTO forensic_results (
                    result_id, evidence_id, integrity_status, provenance_status,
                    ai_manipulation_score, ai_manipulation_indicator, ai_model_name,
                    ai_model_version, model_confidence, model_status,
                    forensic_anomaly_score, forensic_risk_score, risk_category,
                    confidence_score, analyzed_at, raw_metrics_json,
                    summary_narrative, recommendations, ensemble_agreement_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result_id, evidence_id, "VERIFIED", provenance_status,
                    ai_indicator if ai_indicator is not None else 0.0, ai_indicator, ai_model_name,
                    ai_model_version, model_confidence, model_status,
                    forensic_anomaly_score, risk_score, risk_cat,
                    confidence, analyzed_at, json.dumps(raw_metrics, default=_json_safe),
                    narrative_res.get("summary", ""),
                    narrative_res.get("recommendations", ""),
                    json.dumps(ensemble_agreement, default=_json_safe)
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

            # Store DNA fingerprint on evidence row
            cursor.execute("PRAGMA table_info(evidence)")
            ev_cols = [c["name"] for c in cursor.fetchall()]
            if "dna_fingerprint" in ev_cols:
                cursor.execute(
                    "UPDATE evidence SET dna_fingerprint = ? WHERE evidence_id = ?",
                    (dna_record["dna_fingerprint"], evidence_id)
                )

            cursor.execute("""
            UPDATE evidence
            SET status = 'COMPLETED', pipeline_status = 'COMPLETED', analyzed_at = ?, error_message = NULL
            WHERE evidence_id = ?
            """, (analyzed_at, evidence_id))

        # 12. Record Chain of Custody Events
        ChainOfCustodyLogger.record_event(
            evidence_id=evidence_id,
            action="FORENSIC_ANALYSIS_COMPLETED",
            actor="Truth Lens Forensic Engine",
            recorded_sha256=evidence["sha256_hash"],
            details=f"Multi-specialist analysis executed ({analysis_mode}). {len(findings)} findings logged. Agreement: {ensemble_agreement['consensus_label']}. Sub-type: {manipulation_subtype}."
        )
        ChainOfCustodyLogger.record_event(
            evidence_id=evidence_id,
            action="RISK_ASSESSED",
            actor="Truth Lens Risk Engine",
            recorded_sha256=evidence["sha256_hash"],
            details=f"Forensic Assessment: {forensic_taxonomy.replace('_', ' ')} (Score: {risk_score}/100 - {risk_cat})."
        )


    except Exception as e:
        logger.error(f"Error during forensic analysis of {evidence_id}: {e}", exc_info=True)
        failed_at = datetime.utcnow().isoformat() + "Z"
        safe_error = f"Automated analysis failed during execution: {type(e).__name__}."
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE evidence 
            SET status = 'FAILED', pipeline_status = 'FAILED', error_message = ?, analyzed_at = ? 
            WHERE evidence_id = ?
            """, (safe_error, failed_at, evidence_id))
            cursor.execute("SELECT sha256_hash FROM evidence WHERE evidence_id = ?", (evidence_id,))
            ev_row = cursor.fetchone()
            recorded_hash = ev_row["sha256_hash"] if ev_row else "UNKNOWN"

        ChainOfCustodyLogger.record_event(
            evidence_id=evidence_id,
            action="ANALYSIS_FAILED",
            actor="Truth Lens Forensic Engine",
            recorded_sha256=recorded_hash,
            details=f"Automated pipeline processing failed: {safe_error}"
        )

MAX_BULK_FILES = 10

async def _ingest_single_file_payload(
    file: UploadFile,
    case_id: str,
    uploaded_by: str,
    notes: Optional[str],
    background_tasks: BackgroundTasks,
    analysis_mode: str = "FULL_ANALYSIS"
) -> Dict[str, Any]:
    raw_name = file.filename or "evidence.bin"
    clean_filename = sanitize_filename(raw_name)
    
    # Extension validation
    ext = clean_filename.rsplit(".", 1)[-1].lower() if "." in clean_filename else ""
    if ext not in settings.ALLOWED_EXTENSIONS:
        return {
            "status": "REJECTED",
            "original_filename": clean_filename,
            "error": f"Unsupported file extension '.{ext}'. Allowed types: {', '.join(sorted(list(settings.ALLOWED_EXTENSIONS))[:6])}..."
        }

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
                return {
                    "status": "REJECTED",
                    "original_filename": clean_filename,
                    "error": f"File size exceeds maximum upload limit ({settings.MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB)."
                }
            f.write(chunk)

    if file_size == 0:
        if target_path.exists():
            os.remove(target_path)
        return {
            "status": "REJECTED",
            "original_filename": clean_filename,
            "error": "Empty (0 byte) file payload cannot be ingested as forensic evidence."
        }

    mime_type, modality = detect_mime_and_modality(target_path, clean_filename)
    hashes = calculate_file_hashes(target_path)
    uploaded_at = datetime.utcnow().isoformat() + "Z"

    initial_stages = {
        "INTEGRITY_BASELINE": {"stage_key": "INTEGRITY_BASELINE", "status": "COMPLETED", "details": f"SHA-256 calculated ({hashes['sha256'][:16]}...)"},
        "METADATA_PROVENANCE": {"stage_key": "METADATA_PROVENANCE", "status": "QUEUED", "details": "Queued for metadata extraction"},
        "AI_DETECTOR_ENSEMBLE": {"stage_key": "AI_DETECTOR_ENSEMBLE", "status": "QUEUED", "details": "Queued for multi-specialist ensemble"},
        "PIXEL_FORENSICS": {"stage_key": "PIXEL_FORENSICS", "status": "QUEUED", "details": "Queued for ELA & noise residual"},
        "LOCAL_REGION_ANALYSIS": {"stage_key": "LOCAL_REGION_ANALYSIS", "status": "QUEUED", "details": "Queued for patch localizer"},
        "EXTERNAL_DETECTORS": {"stage_key": "EXTERNAL_DETECTORS", "status": "QUEUED", "details": "Queued for external corroboration"},
        "EVIDENCE_CORRELATION": {"stage_key": "EVIDENCE_CORRELATION", "status": "QUEUED", "details": "Queued for evidence synthesis"}
    }

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
            uploaded_by, uploaded_at, status, pipeline_status, analysis_started_at, notes,
            analysis_mode, pipeline_stages_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            evidence_id, case_id, clean_filename, stored_filename, modality,
            mime_type, file_size, hashes["sha256"], hashes["sha512"], hashes["md5"],
            uploaded_by, uploaded_at, "ANALYZING", "ANALYZING", uploaded_at, notes or "",
            analysis_mode, json.dumps(initial_stages)
        ))

    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="EVIDENCE_INGESTION",
        actor=uploaded_by,
        recorded_sha256=hashes["sha256"],
        details=f"Exhibit '{clean_filename}' ingested (Mode: {analysis_mode}) into {case_id}. Baseline SHA-256 fingerprint recorded."
    )

    # Dispatch pipeline in background task
    background_tasks.add_task(execute_forensic_pipeline, evidence_id)

    return {
        "status": "ACCEPTED",
        "evidence_id": evidence_id,
        "case_id": case_id,
        "original_filename": clean_filename,
        "modality": modality,
        "mime_type": mime_type,
        "file_size_bytes": file_size,
        "sha256_hash": hashes["sha256"],
        "analysis_mode": analysis_mode,
        "message": "Evidence ingested. Background multi-specialist forensic pipeline in progress."
    }

@router.post("/upload", status_code=202)
async def upload_evidence(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    case_id: str = Form("CASE-2026-001"),
    uploaded_by: str = Form("Digital Forensics Investigator"),
    notes: Optional[str] = Form(""),
    analysis_mode: str = Form("FULL_ANALYSIS")
):
    res = await _ingest_single_file_payload(file, case_id, uploaded_by, notes, background_tasks, analysis_mode)
    if res["status"] == "REJECTED":
        raise HTTPException(status_code=400, detail=res["error"])
    return {
        "evidence_id": res["evidence_id"],
        "case_id": res["case_id"],
        "original_filename": res["original_filename"],
        "modality": res["modality"],
        "mime_type": res["mime_type"],
        "file_size_bytes": res["file_size_bytes"],
        "sha256_hash": res["sha256_hash"],
        "status": "ANALYZING",
        "analysis_mode": res.get("analysis_mode", analysis_mode),
        "message": res["message"]
    }

@router.post("/upload-bulk", status_code=202, response_model=BulkUploadResponse)
async def upload_bulk_evidence(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    case_id: str = Form("CASE-2026-001"),
    uploaded_by: str = Form("Digital Forensics Investigator"),
    notes: Optional[str] = Form(""),
    analysis_mode: str = Form("FULL_ANALYSIS")
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for upload.")
    if len(files) > MAX_BULK_FILES:
        raise HTTPException(status_code=400, detail=f"Maximum of {MAX_BULK_FILES} files allowed per bulk upload batch. (Received {len(files)}).")

    items = []
    accepted = 0
    rejected = 0

    for f in files:
        item_res = await _ingest_single_file_payload(f, case_id, uploaded_by, notes, background_tasks, analysis_mode)
        if item_res["status"] == "ACCEPTED":
            accepted += 1
            items.append(BulkUploadItemResponse(
                status="ACCEPTED",
                evidence_id=item_res["evidence_id"],
                original_filename=item_res["original_filename"],
                modality=item_res["modality"],
                mime_type=item_res["mime_type"],
                file_size_bytes=item_res["file_size_bytes"],
                sha256_hash=item_res["sha256_hash"]
            ))
        else:
            rejected += 1
            items.append(BulkUploadItemResponse(
                status="REJECTED",
                original_filename=item_res["original_filename"],
                error=item_res.get("error", "Validation failed.")
            ))

    return BulkUploadResponse(
        case_id=case_id,
        total_files=len(files),
        accepted_count=accepted,
        rejected_count=rejected,
        items=items,
        message=f"Bulk upload processed ({analysis_mode}): {accepted} file(s) accepted into background pipeline, {rejected} rejected."
    )

@router.get("/{evidence_id}/pipeline-progress", response_model=PipelineProgressResponse)
def get_pipeline_progress(evidence_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT evidence_id, status, pipeline_status, analysis_mode, pipeline_stages_json, analyzed_at FROM evidence WHERE evidence_id = ?", (evidence_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Evidence not found.")
        
        stages = {}
        if row.get("pipeline_stages_json"):
            try:
                stages = json.loads(row["pipeline_stages_json"])
            except Exception:
                pass
        
        current_stage = "COMPLETED" if row["status"] == "COMPLETED" else ("FAILED" if row["status"] == "FAILED" else "INITIALIZING")
        for k, v in stages.items():
            if v.get("status") == "ANALYZING":
                current_stage = k
                break

        return {
            "evidence_id": row["evidence_id"],
            "status": row["status"],
            "analysis_mode": row.get("analysis_mode", "FULL_ANALYSIS") or "FULL_ANALYSIS",
            "pipeline_status": row.get("pipeline_status", row["status"]),
            "current_stage": current_stage,
            "stages": stages,
            "analyzed_at": row.get("analyzed_at")
        }

@router.get("/{evidence_id}/status", response_model=EvidenceStatusResponse)
def get_evidence_status(evidence_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT evidence_id, status, pipeline_status, modality, original_filename, 
               uploaded_at, analysis_started_at, analyzed_at, error_message, analysis_mode, pipeline_stages_json 
        FROM evidence WHERE evidence_id = ?
        """, (evidence_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Evidence not found.")
        
        status_val = row["status"]
        stages = {}
        if row.get("pipeline_stages_json"):
            try:
                stages = json.loads(row["pipeline_stages_json"])
            except Exception:
                pass

        return {
            "evidence_id": row["evidence_id"],
            "status": status_val,
            "pipeline_status": row.get("pipeline_status", status_val),
            "analysis_mode": row.get("analysis_mode", "FULL_ANALYSIS") or "FULL_ANALYSIS",
            "modality": row["modality"],
            "original_filename": row["original_filename"],
            "uploaded_at": row["uploaded_at"],
            "analysis_started_at": row.get("analysis_started_at"),
            "analyzed_at": row.get("analyzed_at"),
            "error_message": row.get("error_message") if status_val == "FAILED" else None,
            "pipeline_stages": stages
        }

@router.get("/{evidence_id}/frames")
def get_evidence_frames(evidence_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT raw_metrics_json FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        row = cursor.fetchone()
        if not row:
            return {"evidence_id": evidence_id, "frames_count": 0, "frames": []}
        try:
            raw_metrics = json.loads(row["raw_metrics_json"])
            saved = raw_metrics.get("saved_sample_frames", [])
            frames = [
                {
                    "frame_index": f.get("frame_index", 0),
                    "rank": f.get("rank", 0),
                    "timestamp_sec": f.get("timestamp_sec", 0.0),
                    "artifact_url": f"/api/evidence/{evidence_id}/forensic-artifact/video_frame_{f.get('rank', 0)}"
                }
                for f in saved
            ]
            return {"evidence_id": evidence_id, "frames_count": len(frames), "frames": frames}
        except Exception:
            return {"evidence_id": evidence_id, "frames_count": 0, "frames": []}

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

        # 1. Evidence
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

        # 2. Case
        cursor.execute("SELECT * FROM cases WHERE case_id = ?", (evidence["case_id"],))
        case_info = cursor.fetchone()

        # 3. Forensic Results
        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        forensic_result = cursor.fetchone()
        if forensic_result:
            try:
                forensic_result["raw_metrics_json"] = json.loads(forensic_result["raw_metrics_json"])
            except Exception:
                forensic_result["raw_metrics_json"] = {}
            forensic_result["forensic_taxonomy"] = forensic_result["raw_metrics_json"].get("forensic_taxonomy", "ANALYSIS_INCONCLUSIVE")
            forensic_result["ensemble_agreement"] = forensic_result["raw_metrics_json"].get("ensemble_agreement")

        # 4. Findings
        cursor.execute("SELECT * FROM findings WHERE evidence_id = ? ORDER BY score DESC", (evidence_id,))
        findings = cursor.fetchall()

        # 5. Custody Events
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
def verify_evidence_integrity(
    evidence_id: str,
    body: Optional[IntegrityVerificationRequest] = None,
    actor: str = "Lead Forensic Examiner"
):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

    file_path = EVIDENCE_DIR / evidence["stored_filename"]
    has_external_ref = bool(body and body.expected_sha256)
    target_ref = body.expected_sha256 if has_external_ref else evidence["sha256_hash"]

    is_valid, current_sha256, status_msg = verify_integrity(file_path, target_ref)

    if has_external_ref:
        status = "MATCH" if is_valid else "MISMATCH"
        check_type = f"Reference Hash Comparison: {status}"
    else:
        status = "PRESERVED" if is_valid else "MISMATCH"
        check_type = f"Recorded Baseline Fidelity Check: {status}"

    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="INTEGRITY_VERIFIED" if is_valid else "INTEGRITY_VIOLATION_DETECTED",
        actor=actor,
        recorded_sha256=current_sha256,
        details=f"{check_type}. Note: Bitstream integrity check only; does not evaluate content authenticity."
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
    elif artifact_type in ("manipulation_heatmap", "heatmap"):
        p = FORENSIC_DIR / f"manipulation_heatmap_{evidence_id}.png"
        media = "image/png"
    elif artifact_type == "video_frame":
        p = FORENSIC_DIR / f"video_frame_{evidence_id}.jpg"
        media = "image/jpeg"
    elif artifact_type.startswith("video_frame_") and artifact_type.replace("video_frame_", "").isdigit():
        rank = int(artifact_type.replace("video_frame_", ""))
        p = FORENSIC_DIR / f"video_frame_{evidence_id}_{rank}.jpg"
        media = "image/jpeg"
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
        forensic_result = cursor.fetchone()
        if not forensic_result:
            raise HTTPException(status_code=400, detail="Forensic analysis has not completed for this evidence.")

        cursor.execute("SELECT * FROM findings WHERE evidence_id = ? ORDER BY score DESC", (evidence_id,))
        findings = cursor.fetchall()

    try:
        raw_metrics = json.loads(forensic_result["raw_metrics_json"])
    except Exception:
        raw_metrics = {}

    explanation_data = ForensicCopilot.generate_structured_explanation(
        evidence_id=evidence_id,
        evidence_data=dict(evidence),
        forensic_result=dict(forensic_result),
        findings=[dict(f) for f in findings]
    )

    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="AI_EXPLANATION_GENERATED",
        actor=actor,
        recorded_sha256=evidence["sha256_hash"],
        details=f"Forensic copilot explanation generated via {explanation_data.get('source', 'Local Deterministic Engine')}."
    )

    return AIExplanationResponse(
        evidence_id=evidence_id,
        investigator_summary=explanation_data.get("investigator_summary", ""),
        technical_findings_requiring_review=explanation_data.get("technical_findings_requiring_review", []),
        limitations=explanation_data.get("limitations", ""),
        recommended_next_steps=explanation_data.get("recommended_next_steps", []),
        disclaimer=explanation_data.get("disclaimer", ""),
        source=explanation_data.get("source", "Local Deterministic Engine"),
        timestamp=explanation_data.get("timestamp", datetime.utcnow().isoformat() + "Z")
    )


@router.get("/{evidence_id}/dna")
def get_evidence_dna(evidence_id: str):
    """
    Returns the Evidence DNA forensic fingerprint for this exhibit.
    Includes camera provenance, compression, metadata richness, and signal summary counts.
    Also checks if the same file was seen in a prior upload.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        forensic_result = cursor.fetchone()

    raw_metrics = {}
    provenance_res = {}
    if forensic_result:
        try:
            raw_metrics = json.loads(forensic_result.get("raw_metrics_json") or "{}")
        except Exception:
            pass
        provenance_res = raw_metrics.get("provenance", {})

    # Check for existing DNA in evidence row first
    stored_dna_fp = evidence.get("dna_fingerprint")

    # Build fresh (or from stored metrics)
    dna = EvidenceDNA.build_dna(
        evidence_id=evidence_id,
        sha256_hash=evidence["sha256_hash"],
        original_filename=evidence["original_filename"],
        modality=evidence["modality"],
        file_size_bytes=evidence["file_size_bytes"],
        raw_metrics=raw_metrics,
        provenance_result=provenance_res
    )

    # Check for known/duplicate file
    dna_fp = stored_dna_fp or dna["dna_fingerprint"]
    known_match = EvidenceDNA.check_known_file(dna_fp, evidence_id)
    dna["known_file_match"] = known_match

    return dna


@router.get("/{evidence_id}/confidence-matrix")
def get_confidence_matrix(evidence_id: str):
    """
    Returns the 6-axis Forensic Confidence Matrix (AI Models, Pixel Forensics, Metadata,
    Provenance, Region Analysis, Signal Agreement). No new computation — derived from existing results.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        forensic_result = cursor.fetchone()
        if not forensic_result:
            raise HTTPException(status_code=400, detail="Forensic analysis has not completed for this evidence.")

        cursor.execute("SELECT * FROM findings WHERE evidence_id = ? ORDER BY score DESC", (evidence_id,))
        findings = cursor.fetchall()

    try:
        raw_metrics = json.loads(forensic_result.get("raw_metrics_json") or "{}")
    except Exception:
        raw_metrics = {}

    try:
        ensemble_agreement = json.loads(forensic_result.get("ensemble_agreement_json") or "{}")
    except Exception:
        ensemble_agreement = {}

    forensic_taxonomy = raw_metrics.get("forensic_taxonomy") or raw_metrics.get("risk_components", {}).get("forensic_taxonomy", "ANALYSIS_INCONCLUSIVE")

    matrix = ConfidenceMatrix.build(
        forensic_risk_score=forensic_result.get("forensic_risk_score", 0.0),
        risk_category=forensic_result.get("risk_category", "REVIEW REQUIRED"),
        forensic_taxonomy=forensic_taxonomy,
        ensemble_agreement=ensemble_agreement,
        provenance_status=forensic_result.get("provenance_status", "NOT_AVAILABLE"),
        findings=[dict(f) for f in findings],
        raw_metrics=raw_metrics
    )

    return {
        "evidence_id": evidence_id,
        "risk_category": forensic_result.get("risk_category"),
        "forensic_taxonomy": forensic_taxonomy,
        "manipulation_subtype": forensic_result.get("manipulation_subtype", "INCONCLUSIVE"),
        "matrix": matrix
    }


@router.post("/{evidence_id}/robustness-test")
def run_robustness_test(evidence_id: str):
    """
    Run the Adversarial Robustness Stress Test on an IMAGE evidence item.
    Applies 7 transforms (JPEG compression, resize, blur, sharpen, screenshot simulation,
    social media compression) and tests whether forensic signals persist.
    Original file is never modified.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

        if evidence.get("modality") != "IMAGE":
            raise HTTPException(status_code=400, detail="Robustness stress test is only available for IMAGE modality evidence.")

        if evidence.get("status") != "COMPLETED":
            raise HTTPException(status_code=400, detail="Forensic analysis must be completed before running robustness test.")

        cursor.execute("SELECT forensic_risk_score, risk_category FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        fr = cursor.fetchone()

    file_path = EVIDENCE_DIR / evidence["stored_filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Evidence file not found on disk.")

    original_verdict = fr["risk_category"] if fr else "REVIEW REQUIRED"
    original_score = float(fr["forensic_risk_score"]) if fr else 0.0

    result = RobustnessTester.run(
        file_path=file_path,
        evidence_id=evidence_id,
        original_verdict=original_verdict,
        original_score=original_score
    )

    # Store result as a forensic artifact
    try:
        import json as _json
        rob_path = FORENSIC_DIR / f"{evidence_id}_robustness.json"
        with open(rob_path, "w") as rf:
            _json.dump(result, rf, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist robustness result: {e}")

    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="ROBUSTNESS_TEST_EXECUTED",
        actor="Truth Lens Robustness Engine",
        recorded_sha256=evidence["sha256_hash"],
        details=f"Adversarial robustness test: {result.get('consistent_transforms', 0)}/{result.get('total_transforms', 0)} transforms consistent. Robustness: {result.get('robustness_label', 'N/A')}."
    )

    return result


@router.get("/{evidence_id}/verify-chain")
def verify_custody_chain(evidence_id: str):
    """
    Walk the hash-chained custody audit log for this evidence item and verify each link.
    Returns CHAIN_VALID or CHAIN_BROKEN with details of any detected tampering.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT evidence_id FROM evidence WHERE evidence_id = ?", (evidence_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Evidence not found.")

    return ChainOfCustodyLogger.verify_chain(evidence_id)
