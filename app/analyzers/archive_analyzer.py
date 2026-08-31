import os
import hashlib
import zipfile
import tarfile
from pathlib import Path
from typing import Dict, Any, List

from app.analyzers.base_analyzer import BaseAnalyzer
from app.core.explainability import FindingBuilder
from app.security.validator import validate_archive_security

class ArchiveAnalyzer(BaseAnalyzer):
    """
    Forensic Archive Analyzer for ZIP, TAR, and GZ containers.
    Performs nested SHA-256 fingerprinting, Zip Slip validation, and embedded payload scanning.
    """

    def analyze(self, file_path: Path, evidence_id: str) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        raw_metrics: Dict[str, Any] = {}
        nested_hashes: Dict[str, str] = {}
        suspicious_extensions = {".exe", ".bat", ".cmd", ".vbs", ".ps1", ".scr", ".dll", ".so", ".dylib", ".js"}

        # 1. Security Check (Zip Slip & Zip Bomb Guard)
        validate_archive_security(file_path)

        suspicious_files_found = []
        total_files = 0
        total_unpacked_size = 0

        try:
            is_zip = zipfile.is_zipfile(file_path)
        except Exception:
            is_zip = False

        is_tar = False
        if not is_zip:
            try:
                is_tar = tarfile.is_tarfile(file_path)
            except Exception:
                is_tar = False

        if not (is_zip or is_tar):
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Unrecognized or Corrupted Archive Container",
                category="SIGNAL_ANALYSIS",
                severity="MEDIUM",
                score=50.0,
                explanation="The file is not a valid ZIP or TAR archive or the container is corrupted."
            ))
            return {
                "ai_model_name": None,
                "ai_model_version": None,
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": "ANALYSIS UNAVAILABLE",
                "forensic_anomaly_score": 50.0,
                "signal_anomalies_score": 50.0,
                "metadata_anomaly_score": 50.0,
                "findings": findings,
                "raw_metrics": raw_metrics
            }

        if is_zip:
            with zipfile.ZipFile(file_path, 'r') as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    total_files += 1
                    total_unpacked_size += member.file_size
                    
                    # Stream member bytes for sha256 to avoid high memory allocation
                    hasher = hashlib.sha256()
                    with zf.open(member.filename) as mf:
                        while chunk := mf.read(65536):
                            hasher.update(chunk)
                    nested_hashes[member.filename] = hasher.hexdigest()

                    ext = os.path.splitext(member.filename)[1].lower()
                    if ext in suspicious_extensions:
                        suspicious_files_found.append(member.filename)
        
        elif is_tar:
            with tarfile.open(file_path, 'r:*') as tf:
                for member in tf.getmembers():
                    if member.isdir():
                        continue
                    total_files += 1
                    total_unpacked_size += member.size
                    
                    f = tf.extractfile(member)
                    if f:
                        try:
                            hasher = hashlib.sha256()
                            while chunk := f.read(65536):
                                hasher.update(chunk)
                            nested_hashes[member.name] = hasher.hexdigest()

                            ext = os.path.splitext(member.name)[1].lower()
                            if ext in suspicious_extensions:
                                suspicious_files_found.append(member.name)
                        finally:
                            f.close()

        raw_metrics["total_nested_files"] = total_files
        raw_metrics["total_unpacked_size_bytes"] = total_unpacked_size
        raw_metrics["nested_file_hashes"] = nested_hashes

        signal_score = 10.0
        if suspicious_files_found:
            signal_score = 85.0
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Executable Payloads Inside Archive",
                category="SIGNAL_ANALYSIS",
                severity="CRITICAL",
                score=90.0,
                explanation=f"Found {len(suspicious_files_found)} executable/script files inside archive: {', '.join(suspicious_files_found[:3])}.",
                location_ref="Archive Root"
            ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Safe Archive Structure Verified",
                category="SIGNAL_ANALYSIS",
                severity="INFO",
                score=10.0,
                explanation=f"Verified {total_files} nested files with individual SHA-256 fingerprints. No path traversal or malicious binaries found."
            ))

        return {
            "ai_model_name": None,
            "ai_model_version": None,
            "ai_manipulation_indicator": None,
            "model_confidence": None,
            "model_status": "ANALYSIS UNAVAILABLE",
            "forensic_anomaly_score": signal_score,
            "signal_anomalies_score": signal_score,
            "metadata_anomaly_score": 10.0,
            "findings": findings,
            "raw_metrics": raw_metrics
        }
