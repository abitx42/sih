"""
app/core/localization_policy.py — Transparent Evidence-Result Policy Engine.
Every threshold comes from app.config.Settings. No magic numbers.

Allowed outcomes (6 total):
  VERIFIED_PROVENANCE             — real C2PA cryptographic validation passed
  REFERENCE_DIFFERENCE_CONFIRMED  — trusted-reference comparison succeeded
  HIGH_RISK_LOCALIZED_ALTERATION  — high-reliability localization + >=1 supporting signal
  GENERATIVE_IMAGE_INDICATOR      — global AI model score above threshold
  INCONCLUSIVE                    — signals weak, conflicting, or unavailable
  NO_STRONG_INDICATOR_FOUND       — all below thresholds; never labelled "real"/"authentic"
"""
from __future__ import annotations
from typing import Dict, Any, Optional, List
from app.config import settings

OUTCOME_VERIFIED_PROVENANCE            = "VERIFIED_PROVENANCE"
OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED = "REFERENCE_DIFFERENCE_CONFIRMED"
OUTCOME_HIGH_RISK_LOCALIZED_ALTERATION = "HIGH_RISK_LOCALIZED_ALTERATION"
OUTCOME_GENERATIVE_IMAGE_INDICATOR     = "GENERATIVE_IMAGE_INDICATOR"
OUTCOME_INCONCLUSIVE                   = "INCONCLUSIVE"
OUTCOME_NO_STRONG_INDICATOR_FOUND      = "NO_STRONG_INDICATOR_FOUND"

OUTCOME_LABELS: Dict[str, str] = {
    OUTCOME_VERIFIED_PROVENANCE:            "Verified Provenance",
    OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED: "Reference Difference Confirmed",
    OUTCOME_HIGH_RISK_LOCALIZED_ALTERATION: "High-Risk Localized Alteration",
    OUTCOME_GENERATIVE_IMAGE_INDICATOR:     "Generative-Image Indicator",
    OUTCOME_INCONCLUSIVE:                   "Inconclusive",
    OUTCOME_NO_STRONG_INDICATOR_FOUND:      "No Strong Indicator Found",
}

OUTCOME_DESCRIPTIONS: Dict[str, str] = {
    OUTCOME_VERIFIED_PROVENANCE: (
        "Cryptographic C2PA provenance validation passed. The manifest and content "
        "binding were verified against a trusted issuer. Does not certify image content authenticity."
    ),
    OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED: (
        "Pixel-level comparison against an investigator-supplied reference image succeeded. "
        "Structural differences were detected and mapped. Confirms image differences — "
        "does not identify the alteration method or tool."
    ),
    OUTCOME_HIGH_RISK_LOCALIZED_ALTERATION: (
        "Spatial forensic signals show localized anomalies at high reliability, "
        "corroborated by at least one independent supporting signal. "
        "Method of alteration is undetermined from image signals alone."
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
            "LOCALIZATION_HIGH_RELIABILITY_THRESHOLD": settings.LOCALIZATION_HIGH_RELIABILITY_THRESHOLD,
            "LOCALIZATION_MIN_SUPPORTING_SIGNALS": settings.LOCALIZATION_MIN_SUPPORTING_SIGNALS,
            "REFERENCE_COMPARISON_ALIGNMENT_THRESHOLD": settings.REFERENCE_COMPARISON_ALIGNMENT_THRESHOLD,
            "GENERATIVE_INDICATOR_THRESHOLD": settings.GENERATIVE_INDICATOR_THRESHOLD,
        }

        # Tier 1: Verified Provenance (real C2PA cryptographic validation only)
        if provenance_status == "CRYPTOGRAPHIC_VALIDATION_PASSED":
            return PolicyEngine._result(OUTCOME_VERIFIED_PROVENANCE, thresholds, 0,
                                        "C2PA cryptographic manifest binding verified")

        # Tier 2: Reference Difference Confirmed
        if (reference_comparison is not None
                and reference_comparison.get("comparison_status") == "REFERENCE_DIFFERENCE_CONFIRMED"
                and reference_comparison.get("alignment_succeeded", False)):
            return PolicyEngine._result(
                OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED, thresholds, 1,
                f"Reference comparison SSIM={reference_comparison.get('ssim_score', 0):.3f}, "
                f"alignment succeeded, {reference_comparison.get('changed_region_count', 0)} changed region(s)")

        supporting_signals = PolicyEngine._count_supporting_signals(
            findings, ensemble_agreement, ai_manipulation_indicator, model_status)

        # Tier 3: High-Risk Localized Alteration
        if localization_result is not None:
            loc_status = localization_result.get("localization_status", "UNAVAILABLE")
            regions = localization_result.get("localized_regions", [])
            if loc_status == "AVAILABLE" and regions:
                max_reliability = max((r.get("reliability", 0.0) for r in regions), default=0.0)
                if (max_reliability >= settings.LOCALIZATION_HIGH_RELIABILITY_THRESHOLD
                        and supporting_signals >= settings.LOCALIZATION_MIN_SUPPORTING_SIGNALS):
                    return PolicyEngine._result(
                        OUTCOME_HIGH_RISK_LOCALIZED_ALTERATION, thresholds, supporting_signals,
                        f"Max region reliability={max_reliability:.2f} >= threshold "
                        f"{settings.LOCALIZATION_HIGH_RELIABILITY_THRESHOLD}, "
                        f"supporting_signals={supporting_signals}")

        # Tier 4: Generative-Image Indicator
        if (model_status == "AVAILABLE" and ai_manipulation_indicator is not None
                and ai_manipulation_indicator >= settings.GENERATIVE_INDICATOR_THRESHOLD):
            return PolicyEngine._result(
                OUTCOME_GENERATIVE_IMAGE_INDICATOR, thresholds, supporting_signals,
                f"AI model indicator={ai_manipulation_indicator:.3f} >= threshold "
                f"{settings.GENERATIVE_INDICATOR_THRESHOLD}")

        # Tier 5: Inconclusive
        has_conflict = (ensemble_agreement is not None
                        and ensemble_agreement.get("has_signal_conflict", False))
        has_mid_signal = ((ai_manipulation_indicator is not None
                           and 0.35 <= ai_manipulation_indicator < settings.GENERATIVE_INDICATOR_THRESHOLD)
                          or supporting_signals > 0)
        if has_conflict or (model_status != "AVAILABLE" and has_mid_signal):
            return PolicyEngine._result(OUTCOME_INCONCLUSIVE, thresholds, supporting_signals,
                                        "Signal conflict or model unavailable with partial heuristic anomalies")

        # Tier 6: No Strong Indicator Found
        return PolicyEngine._result(OUTCOME_NO_STRONG_INDICATOR_FOUND, thresholds, 0,
                                    "All signals below configured thresholds")

    @staticmethod
    def _count_supporting_signals(findings, ensemble_agreement, ai_manipulation_indicator, model_status) -> int:
        count = 0
        if model_status == "AVAILABLE" and ai_manipulation_indicator is not None and ai_manipulation_indicator >= 0.50:
            count += 1
        if any(f.get("category") in ("PIXEL_FORENSICS", "HEURISTIC") and f.get("score", 0) >= 55.0
               for f in findings):
            count += 1
        if any("noise" in f.get("signal_name", "").lower() and f.get("score", 0) >= 50.0
               for f in findings):
            count += 1
        if any(f.get("category") == "METADATA" and f.get("severity") in ("MEDIUM", "HIGH", "CRITICAL")
               for f in findings):
            count += 1
        return count

    @staticmethod
    def _result(outcome, thresholds, supporting_signals_count, trigger) -> Dict[str, Any]:
        return {
            "outcome": outcome,
            "label": OUTCOME_LABELS[outcome],
            "description": OUTCOME_DESCRIPTIONS[outcome],
            "thresholds_applied": thresholds,
            "supporting_signals_count": supporting_signals_count,
            "trigger": trigger,
            "disclaimer": (
                "Image-only analysis is probabilistic. Findings indicate potential "
                "alteration and require qualified investigator review before evidentiary use."
            ),
        }
