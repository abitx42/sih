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

        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, 'r') as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    total_files += 1
                    total_unpacked_size += member.file_size
                    
                    # Read member bytes for hash
                    data = zf.read(member.filename)
                    h = hashlib.sha256(data).hexdigest()
                    nested_hashes[member.filename] = h

                    ext = os.path.splitext(member.filename)[1].lower()
                    if ext in suspicious_extensions:
                        suspicious_files_found.append(member.filename)
        
        elif tarfile.is_tarfile(file_path):
            with tarfile.open(file_path, 'r:*') as tf:
                for member in tf.getmembers():
                    if member.isdir():
                        continue
                    total_files += 1
                    total_unpacked_size += member.size
                    
                    f = tf.extractfile(member)
                    if f:
                        data = f.read()
                        h = hashlib.sha256(data).hexdigest()
                        nested_hashes[member.name] = h

                        ext = os.path.splitext(member.name)[1].lower()
                        if ext in suspicious_extensions:
                            suspicious_files_found.append(member.name)

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
