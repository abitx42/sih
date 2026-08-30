"""
app/core/self_learning.py
=========================
Self-Learning Feedback Loop, Active Learning Queue & Dataset Manifest Engine (Phase 4).
"""
from __future__ import annotations

import io
import json
import shutil
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from app.config import EVIDENCE_DIR, STORAGE_DIR, settings
from app.database import get_db

logger = logging.getLogger(__name__)

TRAINING_STORE_DIR = STORAGE_DIR / "training_data"
TRAINING_REAL_DIR = TRAINING_STORE_DIR / "real"
TRAINING_AI_DIR = TRAINING_STORE_DIR / "ai_generated"

for d in [TRAINING_STORE_DIR, TRAINING_REAL_DIR, TRAINING_AI_DIR]:
    d.mkdir(parents=True, exist_ok=True)

TARGET_RETRAIN_THRESHOLD = 500


class SelfLearningEngine:
    """
    Continuous Learning & Active Learning Engine for Truth Lens.
    Ingests human investigator feedback to build calibrated training datasets.
    """

    @staticmethod
    def record_review_feedback(
        evidence_id: str,
        verdict: str,
        reviewer_name: str = "Lead Forensic Examiner",
        explicit_label: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Processes an investigator review and saves verified ground-truth to training_dataset.
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
            ev = cursor.fetchone()
            if not ev:
                return None

            cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
            fr = cursor.fetchone()

        if not fr:
            return None

        # Determine ground truth label
        confirmed_label = explicit_label
        ai_indicator = fr.get("ai_manipulation_indicator") or (fr.get("forensic_risk_score", 50.0) / 100.0)
        risk_cat = fr.get("risk_category", "REVIEW REQUIRED")

        if not confirmed_label:
            if verdict == "AGREE":
                confirmed_label = "AI_GENERATED" if (ai_indicator > 0.5 or risk_cat == "HIGH RISK") else "AUTHENTIC_REAL"
            elif verdict == "DISAGREE":
                # False positive / negative correction by examiner
                confirmed_label = "AUTHENTIC_REAL" if (ai_indicator > 0.5 or risk_cat == "HIGH RISK") else "AI_GENERATED"
            elif verdict in ("CONFIRMED_AI", "CONFIRMED_AI_GENERATED"):
                confirmed_label = "AI_GENERATED"
            elif verdict in ("CONFIRMED_REAL", "CONFIRMED_AUTHENTIC"):
                confirmed_label = "AUTHENTIC_REAL"
            else:
                # NEEDS_FURTHER_EXAMINATION: Not yet confirmed ground truth
                return None

        # Copy and anonymize image file for training store (only for IMAGE modality)
        src_path = EVIDENCE_DIR / ev["stored_filename"]
        sample_id = f"TRN-{uuid.uuid4().hex[:10].upper()}"
        ext = Path(ev["stored_filename"]).suffix or ".jpg"
        sub_folder = TRAINING_AI_DIR if confirmed_label == "AI_GENERATED" else TRAINING_REAL_DIR
        dest_path = sub_folder / f"{sample_id}{ext}"

        if src_path.exists() and ev.get("modality", "IMAGE") == "IMAGE":
            try:
                shutil.copy2(src_path, dest_path)
            except Exception as e:
                logger.warning(f"Failed to copy evidence to training dataset store: {e}")
                dest_path = src_path

        now = datetime.utcnow().isoformat() + "Z"

        with get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO training_dataset (
                    sample_id, evidence_id, image_path, confirmed_label,
                    confidence, labeled_by, labeled_at, used_in_training, model_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sample_id,
                evidence_id,
                str(dest_path),
                confirmed_label,
                1.0,
                reviewer_name,
                now,
                0,
                settings.VERSION
            ))

        logger.info(f"SelfLearning: Cataloged sample {sample_id} as {confirmed_label} (by {reviewer_name})")

        return {
            "sample_id": sample_id,
            "evidence_id": evidence_id,
            "confirmed_label": confirmed_label,
            "labeled_by": reviewer_name,
            "labeled_at": now
        }

    @staticmethod
    def get_dataset_statistics() -> Dict[str, Any]:
        """
        Returns training dataset volume, class balance, and retrain readiness.
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM training_dataset")
            total = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) as ai_count FROM training_dataset WHERE confirmed_label = 'AI_GENERATED'")
            ai_count = cursor.fetchone()["ai_count"]

            cursor.execute("SELECT COUNT(*) as real_count FROM training_dataset WHERE confirmed_label = 'AUTHENTIC_REAL'")
            real_count = cursor.fetchone()["real_count"]

            cursor.execute("SELECT COUNT(*) as unused FROM training_dataset WHERE used_in_training = 0")
            unused_count = cursor.fetchone()["unused"]

        queue = SelfLearningEngine.get_active_learning_queue(limit=500)
        queue_size = len(queue)

        readiness_pct = min(100.0, round((total / max(1, TARGET_RETRAIN_THRESHOLD)) * 100.0, 1))

        return {
            "total_samples": total,
            "ai_generated_count": ai_count,
            "authentic_real_count": real_count,
            "unused_in_training": unused_count,
            "active_learning_queue_size": queue_size,
            "target_threshold": TARGET_RETRAIN_THRESHOLD,
            "readiness_percentage": readiness_pct,
            "current_model_version": f"v{settings.VERSION}",
            "retrain_status": "READY_FOR_LORA" if total >= TARGET_RETRAIN_THRESHOLD else "COLLECTING_SAMPLES"
        }

    @staticmethod
    def get_active_learning_queue(limit: int = 20) -> List[Dict[str, Any]]:
        """
        Retrieves samples where model prediction is uncertain (0.35 - 0.65 confidence)
        or there is ensemble conflict, prioritized by highest uncertainty.
        """
        queue = []
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT e.evidence_id, e.original_filename, e.uploaded_at, e.modality,
                           e.file_size_bytes, e.sha256_hash, e.case_id, e.mime_type,
                           fr.forensic_risk_score, fr.risk_category, fr.ai_manipulation_indicator,
                           fr.model_status, fr.raw_metrics_json,
                           r.verdict as existing_verdict
                    FROM evidence e
                    JOIN forensic_results fr ON e.evidence_id = fr.evidence_id
                    LEFT JOIN investigator_reviews r ON e.evidence_id = r.evidence_id
                    WHERE e.status = 'COMPLETED'
                    ORDER BY e.uploaded_at DESC
                """)
                rows = cursor.fetchall()

            for row in rows:
                if row.get("existing_verdict"):
                    # Already reviewed and confirmed
                    continue

                ai_ind = row.get("ai_manipulation_indicator")
                if ai_ind is None:
                    ai_ind = (row.get("forensic_risk_score", 50.0)) / 100.0

                # Uncertainty distance from 0.5 decision boundary
                # Distance = 0.0 means 50% confidence (maximally uncertain)
                dist_from_boundary = abs(ai_ind - 0.5)

                # Flag if uncertain (0.35 - 0.65) or REVIEW REQUIRED
                is_uncertain = (dist_from_boundary <= 0.18) or (row.get("risk_category") == "REVIEW REQUIRED")

                raw_m = {}
                try:
                    raw_m = json.loads(row.get("raw_metrics_json") or "{}")
                except Exception:
                    pass

                conflict = False
                ens_meta = raw_m.get("neural_ensemble", {}).get("ensemble_metadata", {})
                if ens_meta.get("conflict_detected"):
                    conflict = True
                    is_uncertain = True

                if is_uncertain:
                    uncertainty_score = round(max(0.0, 1.0 - (dist_from_boundary * 2.0)), 2)
                    taxonomy = raw_m.get("forensic_taxonomy", row.get("risk_category", "UNCERTAIN"))
                    queue.append({
                        "evidence_id": row["evidence_id"],
                        "filename": row["original_filename"],
                        "original_filename": row["original_filename"],
                        "file_size_bytes": row.get("file_size_bytes", 0),
                        "sha256_hash": row.get("sha256_hash", ""),
                        "case_id": row.get("case_id", "CASE-2026-001"),
                        "mime_type": row.get("mime_type", "image/jpeg"),
                        "modality": row["modality"],
                        "uploaded_at": row["uploaded_at"],
                        "forensic_taxonomy": taxonomy,
                        "ai_indicator": round(float(ai_ind), 3),
                        "ai_manipulation_indicator": round(float(ai_ind), 3),
                        "risk_score": row["forensic_risk_score"],
                        "risk_category": row["risk_category"],
                        "uncertainty_score": uncertainty_score,
                        "ensemble_conflict": conflict,
                        "priority_reason": "Ensemble Conflict Detected" if conflict else f"Borderline Decision Boundary ({round(ai_ind*100, 1)}%)"
                    })

            # Sort by highest uncertainty first
            
            # If no borderline samples found, include recent unreviewed exhibits for training verification
            if len(queue) == 0:
                for row in rows[:limit]:
                    if row.get("existing_verdict"):
                        continue
                    ai_ind = row.get("ai_manipulation_indicator") or (row.get("forensic_risk_score", 50.0) / 100.0)
                    raw_m = {}
                    try:
                        raw_m = json.loads(row.get("raw_metrics_json") or "{}")
                    except Exception:
                        pass
                    taxonomy = raw_m.get("forensic_taxonomy", row.get("risk_category", "UNCERTAIN"))
                    queue.append({
                        "evidence_id": row["evidence_id"],
                        "filename": row["original_filename"],
                        "original_filename": row["original_filename"],
                        "file_size_bytes": row.get("file_size_bytes", 0),
                        "sha256_hash": row.get("sha256_hash", ""),
                        "case_id": row.get("case_id", "CASE-2026-001"),
                        "mime_type": row.get("mime_type", "image/jpeg"),
                        "modality": row["modality"],
                        "uploaded_at": row["uploaded_at"],
                        "forensic_taxonomy": taxonomy,
                        "ai_indicator": round(float(ai_ind), 3),
                        "ai_manipulation_indicator": round(float(ai_ind), 3),
                        "risk_score": row["forensic_risk_score"],
                        "risk_category": row["risk_category"],
                        "uncertainty_score": 0.5,
                        "ensemble_conflict": False,
                        "priority_reason": "Recent Ingested Exhibit"
                    })

            queue.sort(key=lambda x: x["uncertainty_score"], reverse=True)
            return queue[:limit]

        except Exception as e:
            logger.error(f"Active learning queue error: {e}")
            return []

    @staticmethod
    def export_training_manifest() -> Dict[str, Any]:
        """
        Generates PyTorch / HuggingFace ImageFolder training manifest JSON.
        """
        samples = []
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM training_dataset ORDER BY labeled_at ASC")
            rows = cursor.fetchall()

        for r in rows:
            samples.append({
                "sample_id": r["sample_id"],
                "evidence_id": r["evidence_id"],
                "image_path": r["image_path"],
                "label": r["confirmed_label"],
                "label_id": 1 if r["confirmed_label"] == "AI_GENERATED" else 0,
                "confidence": r["confidence"],
                "labeled_by": r["labeled_by"],
                "labeled_at": r["labeled_at"],
                "model_version": r["model_version"]
            })

        return {
            "format": "TruthLens_ImageClassification_Manifest_v1",
            "classes": ["AUTHENTIC_REAL", "AI_GENERATED"],
            "total_samples": len(samples),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "samples": samples
        }
