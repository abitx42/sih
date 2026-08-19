from typing import Dict, Any, List, Tuple, Optional
from app.config import settings

class RiskEngine:
    """
    Deterministic Multi-Signal Forensic Risk Assessment Engine.
    Distinguishes Heuristic Forensic Anomalies from ML Vision Classification Output.
    
    Principles:
    1. SHA-256 integrity only certifies bitstream fidelity against baseline,
       NOT content authenticity.
    2. When ML classification is ANALYSIS UNAVAILABLE, default to REVIEW REQUIRED
       (unless independent critical/high findings demand HIGH RISK), never fabricating an ML score.
    """

    @staticmethod
    def calculate_risk(
        integrity_status: str,
        ai_manipulation_indicator: Optional[float],  # 0.0 to 1.0 or None
        model_status: str,  # AVAILABLE, ANALYSIS UNAVAILABLE, ERROR
        forensic_anomaly_score: float,  # 0.0 to 100.0 (from ELA, FFT, noise)
        metadata_anomaly_score: float,  # 0.0 to 100.0
        provenance_status: str,
        findings: List[Dict[str, Any]]
    ) -> Tuple[float, str, float, Dict[str, float]]:
        """
        Returns:
            (forensic_risk_score, risk_category, confidence_score, component_scores)
        """
        # 1. Integrity Component (0-100)
        # Note: A verified hash only means the file hasn't changed since upload.
        # It does NOT reduce manipulation risk or prove authenticity.
        if integrity_status == "MISMATCH":
            integrity_risk = 100.0
        elif integrity_status == "CORRUPTED":
            integrity_risk = 90.0
        else:
            integrity_risk = 0.0

        # 2. Forensic Signal Anomalies (Heuristic: ELA, FFT, PRNU noise)
        heuristic_risk = max(0.0, min(100.0, forensic_anomaly_score))

        # 3. Metadata Anomalies Component
        meta_risk = max(0.0, min(100.0, metadata_anomaly_score))

        # 4. Provenance Component
        if provenance_status == "VERIFIED":
            provenance_risk = 5.0
        elif provenance_status == "INVALID":
            provenance_risk = 85.0
        elif provenance_status == "NOT_VERIFIED":
            provenance_risk = 45.0
        else:  # NOT_AVAILABLE
            provenance_risk = 20.0

        # 5. ML Manipulation Indicator & Risk Aggregation
        if model_status == "AVAILABLE" and ai_manipulation_indicator is not None:
            ai_risk = max(0.0, min(100.0, ai_manipulation_indicator * 100.0))
            # Weighted formula with ML active:
            # AI ML: 40%, Heuristic Signals: 40%, Metadata: 10%, Provenance: 10%
            final_score = (
                (ai_risk * settings.WEIGHT_AI_MANIPULATION) +
                (heuristic_risk * settings.WEIGHT_FORENSIC_SIGNALS) +
                (meta_risk * settings.WEIGHT_METADATA_ANOMALIES) +
                (provenance_risk * settings.WEIGHT_PROVENANCE)
            )
            is_ml_available = True
        else:
            ai_risk = None
            # ML Unavailable: Do NOT increase heuristic weight excessively.
            # Base risk on heuristic signals (55%), metadata (25%), provenance (20%)
            final_score = (
                (heuristic_risk * 0.55) +
                (meta_risk * 0.25) +
                (provenance_risk * 0.20)
            )
            is_ml_available = False

        # If file tampering detected on disk, override score to maximum
        if integrity_risk > 0:
            final_score = max(final_score, integrity_risk)

        # Critical severity finding check
        critical_count = sum(1 for f in findings if f.get("severity") == "CRITICAL")
        high_count = sum(1 for f in findings if f.get("severity") == "HIGH")
        if critical_count > 0:
            final_score = max(final_score, 75.0)

        final_score = round(max(0.0, min(100.0, final_score)), 1)

        # Categorization logic
        if not is_ml_available:
            # Rule: If ML analysis was UNAVAILABLE, default to REVIEW REQUIRED
            # unless independent high/critical findings justify HIGH RISK.
            if final_score >= 70.0 or critical_count > 0 or high_count >= 2 or integrity_status == "MISMATCH":
                risk_category = "HIGH RISK"
            else:
                risk_category = "REVIEW REQUIRED"
                final_score = max(35.0, final_score)  # Floor at REVIEW REQUIRED threshold
            base_confidence = 0.72  # Lower confidence due to missing ML modality
        else:
            if final_score <= 30.0:
                risk_category = "LOW RISK"
            elif final_score <= 70.0:
                risk_category = "REVIEW REQUIRED"
            else:
                risk_category = "HIGH RISK"
            base_confidence = 0.92 if len(findings) >= 3 else 0.86

        component_scores = {
            "integrity_risk": round(integrity_risk, 1),
            "ai_manipulation_risk": round(ai_risk, 1) if ai_risk is not None else None,
            "forensic_anomaly_risk": round(heuristic_risk, 1),
            "metadata_risk": round(meta_risk, 1),
            "provenance_risk": round(provenance_risk, 1),
            "model_status": model_status
        }

        return final_score, risk_category, base_confidence, component_scores
