from typing import Dict, Any, List, Tuple, Optional
from app.config import settings

class RiskEngine:
    """
    Deterministic Multi-Signal Forensic Risk Assessment Engine.
    Distinguishes Heuristic Forensic Anomalies from ML Vision Classification Output.
    
    Principles:
    1. SHA-256 integrity only certifies bitstream fidelity against baseline,
       NOT content authenticity.
    2. When ML classification is ANALYSIS UNAVAILABLE or ANALYSIS INCONCLUSIVE,
       default to REVIEW REQUIRED (unless independent critical/high findings demand HIGH RISK),
       never fabricating an ML score.
    3. 5-Tier Forensic Authenticity Taxonomy:
       - LIKELY_AUTHENTIC: Uniform noise/compression, baseline EXIF, no localized anomalies.
       - LIKELY_AI_GENERATED: Global synthetic patterns, high ViT confidence across whole frame.
       - LIKELY_AI_ASSISTED_MANIPULATION: Photographic base with localized synthetic edit (e.g. AI eyewear, face swap, inpainting).
       - LIKELY_TRADITIONAL_MANIPULATION: Splicing / Photoshop / cloning without generative synthetic textures.
       - ANALYSIS_INCONCLUSIVE: Conflicting signals, low resolution, or missing reference baseline.
    4. Multi-Specialist Consensus Principle:
       - When independent physical and AI signals strongly conflict (e.g. ViT flags AI, but PRNU noise and EXIF confirm camera capture),
         Truth Lens enforces REVIEW REQUIRED and ANALYSIS_INCONCLUSIVE.
    """

    @staticmethod
    def evaluate_taxonomy(
        integrity_status: str,
        ai_manipulation_indicator: Optional[float],
        model_status: str,
        forensic_anomaly_score: float,
        metadata_anomaly_score: float,
        provenance_status: str,
        findings: List[Dict[str, Any]],
        final_risk_score: float,
        ensemble_agreement: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Determines the 5-tier forensic authenticity taxonomy based on correlated physical signals.
        """
        if integrity_status in ("MISMATCH", "CORRUPTED"):
            return "LIKELY_TRADITIONAL_MANIPULATION"

        if ensemble_agreement and ensemble_agreement.get("has_signal_conflict"):
            return "ANALYSIS_INCONCLUSIVE"

        has_localized_edit = any(
            f.get("category") == "LOCALIZED_MANIPULATION" and f.get("severity") in ("CRITICAL", "HIGH")
            for f in findings
        )
        has_critical_findings = any(f.get("severity") == "CRITICAL" for f in findings)
        has_high_findings = sum(1 for f in findings if f.get("severity") == "HIGH") >= 2

        is_ml_high = (model_status == "AVAILABLE" and ai_manipulation_indicator is not None and ai_manipulation_indicator >= 0.70)
        is_ml_moderate = (model_status == "AVAILABLE" and ai_manipulation_indicator is not None and ai_manipulation_indicator >= 0.40)
        has_ai_metadata = any("generative" in f.get("signal_name", "").lower() or "generative" in f.get("explanation", "").lower() for f in findings)

        # 1. Localized Manipulation (e.g. Sunglasses / Face Inpainting on Photographic Background)
        if has_localized_edit:
            if is_ml_moderate or is_ml_high or has_ai_metadata:
                return "LIKELY_AI_ASSISTED_MANIPULATION"
            return "LIKELY_TRADITIONAL_MANIPULATION"

        # 2. Entire Image Generative Synthesis
        if (is_ml_high and forensic_anomaly_score >= 45.0) or has_ai_metadata:
            return "LIKELY_AI_GENERATED"

        # 3. Traditional Splicing / Metadata / Compression Manipulation
        if (forensic_anomaly_score >= 55.0 or metadata_anomaly_score >= 50.0 or has_critical_findings or has_high_findings):
            return "LIKELY_TRADITIONAL_MANIPULATION"

        # 4. Inconclusive Scenarios
        if model_status == "ANALYSIS INCONCLUSIVE" or (35.0 <= final_risk_score <= 65.0 and (is_ml_moderate or provenance_status == "INVALID")):
            return "ANALYSIS_INCONCLUSIVE"

        # 5. Likely Authentic
        if final_risk_score <= 35.0 and forensic_anomaly_score <= 35.0:
            return "LIKELY_AUTHENTIC"

        if final_risk_score > 65.0:
            return "LIKELY_TRADITIONAL_MANIPULATION"

        return "ANALYSIS_INCONCLUSIVE"

    @staticmethod
    def calculate_risk(
        integrity_status: str,
        ai_manipulation_indicator: Optional[float],  # 0.0 to 1.0 or None
        model_status: str,  # AVAILABLE, ANALYSIS UNAVAILABLE, ANALYSIS INCONCLUSIVE, ERROR
        forensic_anomaly_score: float,  # 0.0 to 100.0 (from ELA, FFT, noise, patch localizer)
        metadata_anomaly_score: float,  # 0.0 to 100.0
        provenance_status: str,
        findings: List[Dict[str, Any]],
        ensemble_agreement: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, str, float, Dict[str, Any]]:
        """
        Returns:
            (forensic_risk_score, risk_category, confidence_score, component_scores)
        """
        # 1. Integrity Component (0-100)
        if integrity_status == "MISMATCH":
            integrity_risk = 100.0
        elif integrity_status == "CORRUPTED":
            integrity_risk = 90.0
        else:
            integrity_risk = 0.0

        # 2. Forensic Signal Anomalies (Heuristic: ELA, FFT, PRNU noise, Patch Localizer)
        heuristic_risk = max(0.0, min(100.0, forensic_anomaly_score))

        # 3. Metadata Anomalies Component
        meta_risk = max(0.0, min(100.0, metadata_anomaly_score))

        # 4. Provenance Component
        if provenance_status == "VERIFIED":
            provenance_risk = 5.0
        elif provenance_status in ("DETECTED_UNVERIFIED_MANIFEST", "UNVALIDATED_MANIFEST") or "DETECTED" in provenance_status or "UNVERIFIED" in provenance_status:
            provenance_risk = 25.0
        elif provenance_status == "INVALID":
            provenance_risk = 85.0
        elif provenance_status == "NOT_VERIFIED":
            provenance_risk = 45.0
        else:  # NOT_AVAILABLE
            provenance_risk = 20.0

        # 5. ML Manipulation Indicator & Risk Aggregation
        if model_status == "AVAILABLE" and ai_manipulation_indicator is not None:
            ai_risk = max(0.0, min(100.0, ai_manipulation_indicator * 100.0))
            final_score = (
                (ai_risk * settings.WEIGHT_AI_MANIPULATION) +
                (heuristic_risk * settings.WEIGHT_FORENSIC_SIGNALS) +
                (meta_risk * settings.WEIGHT_METADATA_ANOMALIES) +
                (provenance_risk * settings.WEIGHT_PROVENANCE)
            )
            is_ml_available = True
        else:
            ai_risk = None
            final_score = (
                (heuristic_risk * 0.55) +
                (meta_risk * 0.25) +
                (provenance_risk * 0.20)
            )
            is_ml_available = False

        # If file tampering detected on disk, override score to maximum
        if integrity_risk > 0:
            final_score = max(final_score, integrity_risk)

        # Critical & Localized finding checks
        critical_count = sum(1 for f in findings if f.get("severity") == "CRITICAL")
        high_count = sum(1 for f in findings if f.get("severity") == "HIGH")
        has_localized = any(f.get("category") == "LOCALIZED_MANIPULATION" for f in findings)

        if critical_count > 0 or (has_localized and heuristic_risk >= 45.0):
            final_score = max(final_score, 75.0)

        final_score = round(max(0.0, min(100.0, final_score)), 1)

        # Check for signal conflict
        has_conflict = bool(ensemble_agreement and ensemble_agreement.get("has_signal_conflict"))

        # Categorization logic
        if has_conflict:
            risk_category = "REVIEW REQUIRED"
            final_score = max(40.0, min(60.0, final_score))
            base_confidence = 0.68
        elif not is_ml_available:
            if final_score >= 70.0 or critical_count > 0 or high_count >= 2 or integrity_status == "MISMATCH":
                risk_category = "HIGH RISK"
            else:
                risk_category = "REVIEW REQUIRED"
                final_score = max(35.0, final_score)
            base_confidence = 0.72
        else:
            if final_score <= 30.0:
                risk_category = "LOW RISK"
            elif final_score <= 70.0:
                risk_category = "REVIEW REQUIRED"
            else:
                risk_category = "HIGH RISK"

            # Boost confidence if multi-specialist consensus is strong
            if ensemble_agreement and ensemble_agreement.get("consensus_verdict") in ("STRONG_MANIPULATION_CONSENSUS", "AUTHENTIC_BASELINE_CONSENSUS"):
                base_confidence = 0.96
            else:
                base_confidence = 0.94 if len(findings) >= 3 else 0.88

        # 6. Evaluate 5-Tier Forensic Taxonomy
        forensic_taxonomy = RiskEngine.evaluate_taxonomy(
            integrity_status=integrity_status,
            ai_manipulation_indicator=ai_manipulation_indicator,
            model_status=model_status,
            forensic_anomaly_score=forensic_anomaly_score,
            metadata_anomaly_score=metadata_anomaly_score,
            provenance_status=provenance_status,
            findings=findings,
            final_risk_score=final_score,
            ensemble_agreement=ensemble_agreement
        )

        # 7. Manipulation Sub-type Classification
        manipulation_subtype = RiskEngine.classify_manipulation_subtype(
            forensic_taxonomy=forensic_taxonomy,
            findings=findings,
            ai_manipulation_indicator=ai_manipulation_indicator,
            model_status=model_status,
            forensic_anomaly_score=forensic_anomaly_score
        )

        component_scores = {
            "integrity_risk": round(integrity_risk, 1),
            "ai_manipulation_risk": round(ai_risk, 1) if ai_risk is not None else None,
            "forensic_anomaly_risk": round(heuristic_risk, 1),
            "metadata_risk": round(meta_risk, 1),
            "provenance_risk": round(provenance_risk, 1),
            "model_status": model_status,
            "forensic_taxonomy": forensic_taxonomy,
            "manipulation_subtype": manipulation_subtype,
            "has_signal_conflict": has_conflict
        }

        if ensemble_agreement:
            component_scores["ensemble_agreement"] = ensemble_agreement

        return final_score, risk_category, base_confidence, component_scores

    @staticmethod
    def classify_manipulation_subtype(
        forensic_taxonomy: str,
        findings: List[Dict[str, Any]],
        ai_manipulation_indicator: Optional[float],
        model_status: str,
        forensic_anomaly_score: float
    ) -> str:
        """
        Emits a specific manipulation sub-type label alongside the 5-tier taxonomy.
        Derived purely from existing signal findings — no new ML calls.
        """
        if forensic_taxonomy == "LIKELY_AUTHENTIC":
            return "NO_MANIPULATION_DETECTED"

        if forensic_taxonomy == "ANALYSIS_INCONCLUSIVE":
            return "INCONCLUSIVE"

        # Keyword signal matching
        signal_names = " ".join(f.get("signal_name", "").lower() for f in findings)
        explanations = " ".join(f.get("explanation", "").lower() for f in findings)
        combined = signal_names + " " + explanations
        cats = [f.get("category", "") for f in findings]

        has_localized = "LOCALIZED_MANIPULATION" in cats
        has_face_signal = any(kw in combined for kw in ("face", "facial", "face region"))
        has_inpainting = any(kw in combined for kw in ("inpainting", "generative fill", "synthetic object", "eyewear", "sunglasses"))
        has_splice = any(kw in combined for kw in ("splice", "splicing", "copy-move", "copy move", "cloning"))
        has_software_edit = any(kw in combined for kw in ("photoshop", "lightroom", "gimp", "editing suite", "post-processing"))
        has_reencode = any(kw in combined for kw in ("reencod", "recompress", "resave", "re-encoded"))
        is_ml_high = model_status == "AVAILABLE" and ai_manipulation_indicator is not None and ai_manipulation_indicator >= 0.70

        if forensic_taxonomy == "LIKELY_AI_GENERATED":
            return "AI_GENERATED"

        if forensic_taxonomy in ("LIKELY_AI_ASSISTED_MANIPULATION", "LIKELY_TRADITIONAL_MANIPULATION"):
            if has_inpainting and has_face_signal:
                return "FACE_REGION_INPAINTING"
            if has_inpainting:
                return "OBJECT_INSERTION"
            if has_face_signal and is_ml_high:
                return "FACE_SWAP"
            if has_splice:
                return "IMAGE_SPLICE"
            if has_software_edit and forensic_anomaly_score >= 40.0:
                return "TRADITIONAL_EDIT"
            if has_localized:
                return "AI_ASSISTED_EDIT"
            if has_reencode:
                return "RE_ENCODED"
            if forensic_taxonomy == "LIKELY_AI_ASSISTED_MANIPULATION":
                return "AI_ASSISTED_EDIT"
            return "TRADITIONAL_EDIT"

        return "INCONCLUSIVE"

