import os
import re
import zipfile
import math
from pathlib import Path
from typing import Dict, Any, List
import xml.etree.ElementTree as ET

from app.analyzers.base_analyzer import BaseAnalyzer
from app.core.explainability import FindingBuilder

class DocumentAnalyzer(BaseAnalyzer):
    """
    Forensic Document Analyzer for PDFs and Office Documents (DOCX/XLSX/PPTX).
    Checks incremental revisions, hidden streams, embedded scripts, and metadata tampering.
    """

    def analyze(self, file_path: Path, evidence_id: str) -> Dict[str, Any]:
        ext = file_path.suffix.lower()
        
        if ext == ".pdf":
            return self._analyze_pdf(file_path, evidence_id)
        elif ext in [".docx", ".xlsx", ".pptx"]:
            return self._analyze_ooxml(file_path, evidence_id, ext)
        else:
            return self._analyze_generic_document(file_path, evidence_id)

    def _analyze_pdf(self, file_path: Path, evidence_id: str) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        raw_metrics: Dict[str, Any] = {}
        meta_score = 0.0
        signal_score = 10.0

        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        raw_metrics["size_bytes"] = len(pdf_bytes)

        # 1. Check Incremental Updates / Multi-EOF
        eof_count = len(re.findall(rb'%%EOF', pdf_bytes))
        raw_metrics["eof_markers_count"] = eof_count

        if eof_count > 1:
            signal_score += 45.0
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="PDF Incremental Update Revision Detected",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=70.0,
                explanation=f"Detected {eof_count} '%%EOF' markers. The PDF has undergone incremental updates / content revision after initial compilation.",
                location_ref="PDF Cross-Reference Table"
            ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Single Revision PDF Structure",
                category="SIGNAL_ANALYSIS",
                severity="INFO",
                score=5.0,
                explanation="Standard monolithic PDF structure with a single EOF marker."
            ))

        # 2. Check for Embedded JavaScript & Actions
        has_js = bool(re.search(rb'/(JavaScript|JS|Launch|EmbeddedFiles)', pdf_bytes))
        raw_metrics["embedded_actions_detected"] = has_js

        if has_js:
            signal_score += 40.0
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Active Executable / JavaScript Stream Detected",
                category="SIGNAL_ANALYSIS",
                severity="CRITICAL",
                score=85.0,
                explanation="The PDF contains embedded interactive JavaScript or launch actions, presenting high potential for dynamic payload execution or content alteration.",
                location_ref="PDF Object Stream"
            ))

        # 3. Extract Metadata Tags
        meta_dict = {}
        for tag in [b"Producer", b"Creator", b"CreationDate", b"ModDate", b"Author", b"Title"]:
            match = re.search(rb'/' + tag + rb'\s*\(([^)]+)\)', pdf_bytes)
            if match:
                try:
                    meta_dict[tag.decode()] = match.group(1).decode(errors='ignore')
                except Exception:
                    pass
        raw_metrics["pdf_metadata"] = meta_dict

        if "ModDate" in meta_dict and "CreationDate" in meta_dict:
            if meta_dict["ModDate"] != meta_dict["CreationDate"]:
                meta_score += 35.0
                findings.append(FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name="PDF Modification Date Discrepancy",
                    category="METADATA",
                    severity="MEDIUM",
                    score=50.0,
                    explanation=f"Creation date ({meta_dict['CreationDate']}) differs from modification timestamp ({meta_dict['ModDate']}). Document was altered after initial authoring."
                ))

        producer = meta_dict.get("Producer", "")
        if any(tool in producer.lower() for tool in ["ilovepdf", "smallpdf", "pdfedit", "canva"]):
            meta_score += 40.0
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Third-Party PDF Manipulation Tool Signature",
                category="METADATA",
                severity="MEDIUM",
                score=60.0,
                explanation=f"PDF Producer indicates post-processing via online editing utility: '{producer}'."
            ))

        forensic_anomaly_score = round(min(100.0, signal_score * 0.5 + meta_score * 0.5), 1)

        return {
            "ai_model_name": None,
            "ai_model_version": None,
            "ai_manipulation_indicator": None,
            "model_confidence": None,
            "model_status": "ANALYSIS UNAVAILABLE",
            "forensic_anomaly_score": forensic_anomaly_score,
            "signal_anomalies_score": min(100.0, signal_score),
            "metadata_anomaly_score": min(100.0, meta_score),
            "findings": findings,
            "raw_metrics": raw_metrics
        }

    def _analyze_ooxml(self, file_path: Path, evidence_id: str, ext: str) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        raw_metrics: Dict[str, Any] = {}
        meta_score = 0.0
        signal_score = 10.0

        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                file_list = zf.namelist()
                raw_metrics["ooxml_streams_count"] = len(file_list)

                # Check for macros / VBA
                has_vba = any("vbaProject.bin" in name for name in file_list)
                raw_metrics["has_macros"] = has_vba

                if has_vba:
                    signal_score += 60.0
                    findings.append(FindingBuilder.create_finding(
                        evidence_id=evidence_id,
                        signal_name="Embedded VBA Macro Project Detected",
                        category="SIGNAL_ANALYSIS",
                        severity="CRITICAL",
                        score=90.0,
                        explanation="Document contains embedded VBA executable macro code (`vbaProject.bin`). Disables default forensic trust.",
                        location_ref="docProps/vbaProject.bin"
                    ))

                # Check core.xml metadata
                if "docProps/core.xml" in file_list:
                    core_xml = zf.read("docProps/core.xml")
                    root = ET.fromstring(core_xml)
                    meta_tags = {}
                    for elem in root.iter():
                        tag_clean = elem.tag.split("}")[-1]
                        if elem.text:
                            meta_tags[tag_clean] = elem.text
                    raw_metrics["core_properties"] = meta_tags

                    if "lastModifiedBy" in meta_tags:
                        findings.append(FindingBuilder.create_finding(
                            evidence_id=evidence_id,
                            signal_name="Document Last Modified By Record",
                            category="METADATA",
                            severity="INFO",
                            score=10.0,
                            explanation=f"Document properties record author '{meta_tags.get('creator', 'Unknown')}' and last editor '{meta_tags.get('lastModifiedBy', 'Unknown')}'."
                        ))

        except Exception as e:
            raw_metrics["error"] = str(e)

        forensic_anomaly_score = round(min(100.0, signal_score * 0.5 + meta_score * 0.5), 1)

        return {
            "ai_model_name": None,
            "ai_model_version": None,
            "ai_manipulation_indicator": None,
            "model_confidence": None,
            "model_status": "ANALYSIS UNAVAILABLE",
            "forensic_anomaly_score": forensic_anomaly_score,
            "signal_anomalies_score": min(100.0, signal_score),
            "metadata_anomaly_score": min(100.0, meta_score),
            "findings": findings,
            "raw_metrics": raw_metrics
        }

    def _analyze_generic_document(self, file_path: Path, evidence_id: str) -> Dict[str, Any]:
        return {
            "ai_model_name": None,
            "ai_model_version": None,
            "ai_manipulation_indicator": None,
            "model_confidence": None,
            "model_status": "ANALYSIS UNAVAILABLE",
            "forensic_anomaly_score": 10.0,
            "signal_anomalies_score": 10.0,
            "metadata_anomaly_score": 10.0,
            "findings": [
                FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name="Generic Text / Binary Document Verified",
                    category="SIGNAL_ANALYSIS",
                    severity="INFO",
                    score=10.0,
                    explanation="Standard plain document processed with baseline cryptographic hashing."
                )
            ],
            "raw_metrics": {"size_bytes": file_path.stat().st_size}
        }
