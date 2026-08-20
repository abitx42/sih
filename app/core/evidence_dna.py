"""
Evidence DNA — Forensic Fingerprint Builder
Computes a deterministic forensic fingerprint for every ingested evidence exhibit.
Detects known/duplicate evidence files across cases.
"""
import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class EvidenceDNA:
    """
    Builds a 'forensic fingerprint' for each evidence file — a structural summary
    combining file identity, camera provenance, compression parameters, and signal metrics
    that uniquely characterizes the evidence without repeating raw findings.
    """

    @staticmethod
    def build_dna(
        evidence_id: str,
        sha256_hash: str,
        original_filename: str,
        modality: str,
        file_size_bytes: int,
        raw_metrics: Dict[str, Any],
        provenance_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build the Evidence DNA fingerprint dict from available forensic data.
        Returns a structured dict suitable for storage and display.
        """
        exif = raw_metrics.get("exif", {})
        dimensions = raw_metrics.get("dimensions", "N/A")
        aspect_ratio = raw_metrics.get("aspect_ratio", None)

        # Camera provenance
        camera_make = exif.get("Make", exif.get("make", ""))
        camera_model = exif.get("Model", exif.get("model", ""))
        if camera_make and camera_model:
            camera_str = f"{camera_make} {camera_model}".strip()
        elif camera_model:
            camera_str = camera_model
        elif camera_make:
            camera_str = camera_make
        else:
            camera_str = "Not Identified"

        # Software (editing suite)
        software = exif.get("Software", exif.get("software", None))

        # Compression / color
        compression = raw_metrics.get("compression_format", None)
        if not compression:
            ext = original_filename.rsplit(".", 1)[-1].upper() if "." in original_filename else modality
            compression = ext

        color_space = exif.get("ColorSpace", exif.get("color_space", None))
        if color_space == 1:
            color_space_str = "sRGB"
        elif color_space == 65535:
            color_space_str = "Uncalibrated"
        elif isinstance(color_space, str):
            color_space_str = color_space
        else:
            color_space_str = "Not Recorded"

        # Metadata richness
        metadata_field_count = len([k for k, v in exif.items() if v is not None]) if exif else 0

        # Provenance
        prov_status = "UNAVAILABLE"
        if provenance_result:
            prov_status = provenance_result.get("status", "UNAVAILABLE")

        # Signal summary counts
        ensemble = raw_metrics.get("ensemble_agreement", {})
        total_specialists = ensemble.get("total_specialists_evaluated", 0)
        manipulated_count = ensemble.get("manipulated_count", 0)
        authentic_count = ensemble.get("authentic_count", 0)

        # Heuristic signal summary
        forensic_anomaly_score = raw_metrics.get("forensic_anomaly_score", raw_metrics.get("signal_anomalies_score", 0.0))
        manipulation_subtype = raw_metrics.get("risk_components", {}).get("manipulation_subtype", "")

        # Compute a stable DNA hash: SHA-256 of identity + structural characteristics
        # This does NOT include analysis results — only file identity + structural metadata
        dna_input = "|".join([
            sha256_hash,
            dimensions,
            str(file_size_bytes),
            camera_str,
            compression,
            str(metadata_field_count)
        ])
        dna_fingerprint = hashlib.sha256(dna_input.encode()).hexdigest()

        return {
            "evidence_id": evidence_id,
            "dna_fingerprint": dna_fingerprint,
            "original_filename": original_filename,
            "modality": modality,
            "file_size_bytes": file_size_bytes,
            "sha256_short": sha256_hash[:32] + "...",
            "sha256_full": sha256_hash,
            "camera": camera_str,
            "software": software,
            "dimensions": dimensions,
            "aspect_ratio": str(aspect_ratio) if aspect_ratio else "N/A",
            "compression": compression,
            "color_space": color_space_str,
            "metadata_field_count": metadata_field_count,
            "provenance_status": prov_status,
            "ai_signals_flagged": manipulated_count,
            "ai_signals_total": total_specialists,
            "manipulation_subtype": manipulation_subtype,
            "forensic_anomaly_score": round(float(forensic_anomaly_score), 1),
            "computed_at": datetime.utcnow().isoformat() + "Z"
        }

    @staticmethod
    def check_known_file(dna_fingerprint: str, exclude_evidence_id: str) -> Optional[Dict[str, Any]]:
        """
        Checks if a matching DNA fingerprint already exists in the database,
        indicating a known or duplicate evidence file.
        Returns the matching record dict, or None if first seen.
        """
        from app.database import get_db
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT evidence_id, original_filename, uploaded_at, case_id FROM evidence "
                    "WHERE dna_fingerprint = ? AND evidence_id != ?",
                    (dna_fingerprint, exclude_evidence_id)
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.warning(f"DNA known-file check failed: {e}")
        return None
