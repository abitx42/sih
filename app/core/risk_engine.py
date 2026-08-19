from typing import Dict, Any, List, Tuple
from app.config import settings

class RiskEngine:
    """
    Deterministic Multi-Signal Forensic Risk Assessment Engine.
    Combines Cryptographic Integrity, AI Detection, Signal Forensics,
    Metadata Anomalies, and Provenance into a transparent 0-100 Forensic Risk Score.
    """

    @staticmethod
    def calculate_risk(
        integrity_status: str,
        ai_manipulation_score: float,  # 0.0 to 1.0
        forensic_signal_anomalies: float,  # 0.0 to 100.0
        metadata_anomaly_score: float,  # 0.0 to 100.0
        provenance_status: str,
        findings: List[Dict[str, Any]]
    ) -> Tuple[float, str, float, Dict[str, float]]:
        """
        Returns:
            (forensic_risk_score, risk_category, confidence_score, component_scores)
        """
        # 1. Integrity Component (0-100)
        # If integrity is MISMATCH, huge red flag on digital chain of custody
        if integrity_status == "MISMATCH":
            integrity_risk = 100.0
        elif integrity_status == "CORRUPTED":
            integrity_risk = 90.0
        else:
            integrity_risk = 0.0

        # 2. AI Manipulation Component (0-100)
        ai_risk = max(0.0, min(100.0, ai_manipulation_score * 100.0))

        # 3. Forensic Signals Component (0-100)
        signal_risk = max(0.0, min(100.0, forensic_signal_anomalies))

        # 4. Metadata Anomalies Component (0-100)
        meta_risk = max(0.0, min(100.0, metadata_anomaly_score))

        # 5. Provenance Component (0-100)
        if provenance_status == "VERIFIED":
            provenance_risk = 5.0
        elif provenance_status == "INVALID":
            provenance_risk = 85.0
        elif provenance_status == "NOT_VERIFIED":
            provenance_risk = 45.0
        else:  # NOT_AVAILABLE
            provenance_risk = 20.0  # Missing provenance is normal for standard camera / messaging files

        # Weighted Sum
        final_score = (
            (integrity_risk * settings.WEIGHT_INTEGRITY) +
            (ai_risk * settings.WEIGHT_AI_MANIPULATION) +
            (signal_risk * settings.WEIGHT_FORENSIC_SIGNALS) +
            (meta_risk * settings.WEIGHT_METADATA_ANOMALIES) +
            (provenance_risk * settings.WEIGHT_PROVENANCE)
        )

        # Critical severity override: If critical integrity failure or extreme AI + signal anomalies, boost
        critical_count = sum(1 for f in findings if f.get("severity") == "CRITICAL")
        if critical_count > 0:
            final_score = max(final_score, 75.0)

        final_score = round(max(0.0, min(100.0, final_score)), 1)

        # Categorize
        if final_score <= 30.0:
            risk_category = "LOW RISK"
        elif final_score <= 70.0:
            risk_category = "REVIEW REQUIRED"
        else:
            risk_category = "HIGH RISK"

        # Confidence assessment based on finding depth
        base_confidence = 0.88
        if len(findings) >= 4:
            base_confidence = 0.94
        elif len(findings) >= 2:
            base_confidence = 0.91

        component_scores = {
            "integrity_risk": round(integrity_risk, 1),
            "ai_risk": round(ai_risk, 1),
            "signal_risk": round(signal_risk, 1),
            "metadata_risk": round(meta_risk, 1),
            "provenance_risk": round(provenance_risk, 1),
            "weights": {
                "integrity": settings.WEIGHT_INTEGRITY,
                "ai_manipulation": settings.WEIGHT_AI_MANIPULATION,
                "forensic_signals": settings.WEIGHT_FORENSIC_SIGNALS,
                "metadata": settings.WEIGHT_METADATA_ANOMALIES,
                "provenance": settings.WEIGHT_PROVENANCE
            }
        }

        return final_score, risk_category, base_confidence, component_scores
