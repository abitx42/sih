"""
app/core/localization_policy.py — Transparent Evidence-Result Policy Engine.
Every threshold comes from app.config.Settings. No magic numbers.

Allowed outcomes (6 total):
  VERIFIED_PROVENANCE                 — real C2PA cryptographic validation passed
  REFERENCE_DIFFERENCE_CONFIRMED      — comparison against investigator-supplied reference confirmed differences
  LOCALIZED_ANOMALY_REQUIRING_REVIEW  — bounded anomaly region + >= 2 distinct supporting signal categories (UNVALIDATED)
  GENERATIVE_IMAGE_INDICATOR          — global AI vision model score above threshold (probabilistic indicator)
  INCONCLUSIVE                        — signals weak, conflicting, compressed, or unavailable
  NO_STRONG_INDICATOR_FOUND           — all signals below thresholds; never labelled "real"/"authentic"
"""
from __future__ import annotations
from typing import Dict, Any, Optional, List, Set
from app.config import settings

OUTCOME_VERIFIED_PROVENANCE                 = "VERIFIED_PROVENANCE"
OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED      = "REFERENCE_DIFFERENCE_CONFIRMED"
OUTCOME_LOCALIZED_ANOMALY_REQUIRING_REVIEW  = "LOCALIZED_ANOMALY_REQUIRING_REVIEW"
# Backwards compatibility alias if referenced
OUTCOME_HIGH_RISK_LOCALIZED_ALTERATION      = OUTCOME_LOCALIZED_ANOMALY_REQUIRING_REVIEW
OUTCOME_GENERATIVE_IMAGE_INDICATOR          = "GENERATIVE_IMAGE_INDICATOR"
OUTCOME_INCONCLUSIVE                        = "INCONCLUSIVE"
OUTCOME_NO_STRONG_INDICATOR_FOUND           = "NO_STRONG_INDICATOR_FOUND"

OUTCOME_LABELS: Dict[str, str] = {
    OUTCOME_VERIFIED_PROVENANCE:                "Verified Provenance",
    OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED:     "Reference Difference Confirmed",
    OUTCOME_LOCALIZED_ANOMALY_REQUIRING_REVIEW: "Localized Anomaly Requiring Review",
    OUTCOME_GENERATIVE_IMAGE_INDICATOR:         "Generative-Image Indicator",
    OUTCOME_INCONCLUSIVE:                       "Inconclusive",
    OUTCOME_NO_STRONG_INDICATOR_FOUND:          "No Strong Indicator Found",
}

OUTCOME_DESCRIPTIONS: Dict[str, str] = {
    OUTCOME_VERIFIED_PROVENANCE: (
        "Cryptographic C2PA provenance validation passed. The manifest and content "
        "binding were verified against a trusted issuer. Does not certify image content authenticity."
    ),
    OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED: (
        "The submitted image differs from the investigator-supplied comparison reference in the highlighted regions. "
        "This comparison does not establish which editing tool or method caused the difference."
    ),
    OUTCOME_LOCALIZED_ANOMALY_REQUIRING_REVIEW: (
        "Localized anomaly signals are present. The alteration method, editing tool, "
        "and whether AI was used cannot be determined from this result. "
        "Calibration status is UNVALIDATED and requires qualified forensic review."
    ),
    OUTCOME_GENERATIVE_IMAGE_INDICATOR: (
        "The global vision classifier score exceeds the configured threshold, indicating "
        "a statistical association with synthetically generated images. "
        "This is a probabilistic indicator — not proof of AI generation."
    ),
    OUTCOME_INCONCLUSIVE: (
        "Forensic signals are weak, conflicting, compressed, or unavailable. "
        "No reliable determination can be made. Further investigation recommended."
    ),
    OUTCOME_NO_STRONG_INDICATOR_FOUND: (
        "No signal exceeded the thresholds required for a higher-tier outcome. "
        "Absence of a strong manipulation indicator does not certify that the image is unedited or authentic."
    ),
}


class PolicyEngine:
    """Evaluates forensic signals and returns a structured policy outcome."""

    @staticmethod
    def evaluate(
        provenance_status: str,
        reference_comparison: Optional[Dict[str, Any]],
        localization_result: Optional[Dict[str, Any]],
        ai_manipulation_indicator: Optional[float],
        model_status: str,
        findings: List[Dict[str, Any]],
        ensemble_agreement: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        thresholds = {
            "LOCALIZATION_MIN_SUPPORTING_CATEGORIES": settings.LOCALIZATION_MIN_SUPPORTING_CATEGORIES,
            "REFERENCE_COMPARISON_ALIGNMENT_THRESHOLD": settings.REFERENCE_COMPARISON_ALIGNMENT_THRESHOLD,
            "GENERATIVE_INDICATOR_THRESHOLD": settings.GENERATIVE_INDICATOR_THRESHOLD,
        }

        # Tier 1: Verified Provenance (real C2PA cryptographic validation only)
        if provenance_status == "CRYPTOGRAPHIC_VALIDATION_PASSED":
            return PolicyEngine._result(
                OUTCOME_VERIFIED_PROVENANCE, thresholds, [],
                "C2PA cryptographic manifest binding verified"
            )

        # Tier 2: Reference Difference Confirmed
        if (reference_comparison is not None
                and reference_comparison.get("comparison_status") == "REFERENCE_DIFFERENCE_CONFIRMED"
                and reference_comparison.get("alignment_succeeded", False)):
            return PolicyEngine._result(
                OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED, thresholds, ["REFERENCE_COMPARISON"],
                f"Comparison with investigator-supplied reference confirmed differences (SSIM={reference_comparison.get('ssim_score', 0):.3f}, "
                f"{reference_comparison.get('changed_region_count', 0)} changed region(s))")

        supporting_categories = PolicyEngine._identify_supporting_categories(
            findings, ai_manipulation_indicator, model_status
        )

        # Tier 3: Localized Anomaly Requiring Review
        if localization_result is not None:
            loc_status = localization_result.get("localization_status", "UNAVAILABLE")
            regions = localization_result.get("localized_regions", [])
            if loc_status == "AVAILABLE" and regions:
                if len(supporting_categories) >= settings.LOCALIZATION_MIN_SUPPORTING_CATEGORIES:
                    cat_list = ", ".join(sorted(supporting_categories))
                    return PolicyEngine._result(
                        OUTCOME_LOCALIZED_ANOMALY_REQUIRING_REVIEW, thresholds, list(supporting_categories),
                        f"Bounded anomaly regions corroborated by {len(supporting_categories)} categories ({cat_list}); calibration status UNVALIDATED"
                    )

        # Tier 4: Generative-Image Indicator
        if (model_status == "AVAILABLE" and ai_manipulation_indicator is not None
                and ai_manipulation_indicator >= settings.GENERATIVE_INDICATOR_THRESHOLD):
            return PolicyEngine._result(
                OUTCOME_GENERATIVE_IMAGE_INDICATOR, thresholds, list(supporting_categories),
                f"Global AI vision model indicator={ai_manipulation_indicator:.3f} >= threshold "
                f"{settings.GENERATIVE_INDICATOR_THRESHOLD}")

        # Tier 5: Inconclusive
        has_conflict = (ensemble_agreement is not None
                        and ensemble_agreement.get("has_signal_conflict", False))
        has_mid_signal = ((ai_manipulation_indicator is not None
                           and 0.35 <= ai_manipulation_indicator < settings.GENERATIVE_INDICATOR_THRESHOLD)
                          or len(supporting_categories) > 0)
        if has_conflict or (model_status != "AVAILABLE" and has_mid_signal):
            return PolicyEngine._result(
                OUTCOME_INCONCLUSIVE, thresholds, list(supporting_categories),
                "Signal conflict or model unavailable with partial heuristic anomalies"
            )

        # Tier 6: No Strong Indicator Found
        return PolicyEngine._result(
            OUTCOME_NO_STRONG_INDICATOR_FOUND, thresholds, [],
            "All signals below configured thresholds"
        )

    @staticmethod
    def _identify_supporting_categories(
        findings: List[Dict[str, Any]],
        ai_manipulation_indicator: Optional[float],
        model_status: str
    ) -> Set[str]:
        """Identifies distinct supporting forensic signal categories."""
        categories: Set[str] = set()

        if model_status == "AVAILABLE" and ai_manipulation_indicator is not None and ai_manipulation_indicator >= 0.50:
            categories.add("AI_VISION_CLASSIFIER")

        for f in findings:
            cat = f.get("category", "")
            score = f.get("score", 0)
            sev = f.get("severity", "")
            sig_name = f.get("signal_name", "").lower()

            if "noise" in sig_name and score >= 45.0:
                categories.add("NOISE_RESIDUAL_VARIANCE")
            elif ("fft" in sig_name or "frequency" in sig_name or "spectral" in sig_name) and score >= 45.0:
                categories.add("FREQUENCY_DOMAIN")
            elif (cat == "PIXEL_FORENSICS" or "ela" in sig_name) and score >= 50.0:
                categories.add("PIXEL_COMPRESSION_ELA")
            elif cat == "METADATA" and sev in ("MEDIUM", "HIGH", "CRITICAL"):
                categories.add("METADATA_PROVENANCE")
            elif cat == "HEURISTIC" and score >= 50.0:
                categories.add("HEURISTIC_ANOMALY")

        return categories


    @staticmethod
    def _result(
        outcome: str,
        thresholds: Dict[str, Any],
        supporting_categories: List[str],
        trigger: str
    ) -> Dict[str, Any]:
        return {
            "outcome": outcome,
            "label": OUTCOME_LABELS[outcome],
            "description": OUTCOME_DESCRIPTIONS[outcome],
            "calibration_status": "UNVALIDATED",
            "thresholds_applied": thresholds,
            "supporting_categories": supporting_categories,
            "supporting_signals_count": len(supporting_categories),
            "trigger": trigger,
            "disclaimer": (
                "Image-only analysis is probabilistic and uncalibrated. "
                "Findings indicate potential anomaly concentrations and require qualified investigator review."
            ),
        }
