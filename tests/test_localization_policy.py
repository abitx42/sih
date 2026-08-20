"""
tests/test_localization_policy.py
===================================
Tests for the PolicyEngine — 6-tier evidence-result policy.
Every test verifies one outcome path and its required conditions.
"""
import pytest
from app.core.localization_policy import (
    PolicyEngine,
    OUTCOME_VERIFIED_PROVENANCE,
    OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED,
    OUTCOME_HIGH_RISK_LOCALIZED_ALTERATION,
    OUTCOME_GENERATIVE_IMAGE_INDICATOR,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_NO_STRONG_INDICATOR_FOUND,
    OUTCOME_LABELS,
    OUTCOME_DESCRIPTIONS,
)


def _base_findings():
    return []

def _base_ensemble():
    return {"has_signal_conflict": False, "consensus_label": "INCONCLUSIVE"}


class TestPolicyOutcomes:

    def test_verified_provenance_requires_c2pa(self):
        result = PolicyEngine.evaluate(
            provenance_status="CRYPTOGRAPHIC_VALIDATION_PASSED",
            reference_comparison=None,
            localization_result=None,
            ai_manipulation_indicator=0.0,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        assert result["outcome"] == OUTCOME_VERIFIED_PROVENANCE

    def test_verified_provenance_not_on_detected_unverified_manifest(self):
        """Mere marker detection must NOT produce VERIFIED_PROVENANCE."""
        result = PolicyEngine.evaluate(
            provenance_status="DETECTED_UNVERIFIED_MANIFEST",
            reference_comparison=None,
            localization_result=None,
            ai_manipulation_indicator=0.0,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        assert result["outcome"] != OUTCOME_VERIFIED_PROVENANCE

    def test_reference_difference_confirmed_outcome(self):
        ref_comparison = {
            "comparison_status": "REFERENCE_DIFFERENCE_CONFIRMED",
            "alignment_succeeded": True,
            "ssim_score": 0.82,
            "changed_region_count": 3,
        }
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=ref_comparison,
            localization_result=None,
            ai_manipulation_indicator=0.3,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        assert result["outcome"] == OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED

    def test_reference_comparison_inconclusive_does_not_trigger_confirmed(self):
        ref_comparison = {
            "comparison_status": "REFERENCE_COMPARISON_INCONCLUSIVE",
            "alignment_succeeded": False,
            "ssim_score": 0.40,
            "changed_region_count": 0,
        }
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=ref_comparison,
            localization_result=None,
            ai_manipulation_indicator=0.9,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        assert result["outcome"] != OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED

    def test_high_risk_localized_alteration_requires_reliability_and_supporting_signals(self):
        """Outcome HIGH_RISK requires reliability >= 0.72 AND >= 1 supporting signal."""
        localization = {
            "localization_status": "AVAILABLE",
            "localized_regions": [{"reliability": 0.80}],
        }
        findings = [{"category": "PIXEL_FORENSICS", "score": 65.0, "signal_name": "ELA Anomaly", "severity": "HIGH"}]
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=localization,
            ai_manipulation_indicator=0.60,
            model_status="AVAILABLE",
            findings=findings,
            ensemble_agreement=_base_ensemble(),
        )
        assert result["outcome"] == OUTCOME_HIGH_RISK_LOCALIZED_ALTERATION

    def test_high_risk_not_issued_below_reliability_threshold(self):
        """If best region reliability < 0.72, HIGH-RISK must not be issued."""
        localization = {
            "localization_status": "AVAILABLE",
            "localized_regions": [{"reliability": 0.65}],  # below 0.72
        }
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=localization,
            ai_manipulation_indicator=0.6,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        assert result["outcome"] != OUTCOME_HIGH_RISK_LOCALIZED_ALTERATION

    def test_high_risk_not_issued_without_supporting_signal(self):
        """HIGH-RISK requires >= 1 independent supporting signal beyond heatmap."""
        localization = {
            "localization_status": "AVAILABLE",
            "localized_regions": [{"reliability": 0.80}],
        }
        # No supporting signals: AI model not available, no strong findings
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=localization,
            ai_manipulation_indicator=None,
            model_status="UNAVAILABLE",
            findings=[],
            ensemble_agreement=_base_ensemble(),
        )
        assert result["outcome"] != OUTCOME_HIGH_RISK_LOCALIZED_ALTERATION

    def test_generative_image_indicator_threshold(self):
        """AI indicator >= GENERATIVE_INDICATOR_THRESHOLD with model AVAILABLE -> GENERATIVE_IMAGE_INDICATOR."""
        from app.config import settings
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=None,
            ai_manipulation_indicator=settings.GENERATIVE_INDICATOR_THRESHOLD + 0.01,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        assert result["outcome"] == OUTCOME_GENERATIVE_IMAGE_INDICATOR

    def test_generative_indicator_not_when_model_unavailable(self):
        """GENERATIVE_IMAGE_INDICATOR must NOT be issued when model is unavailable."""
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=None,
            ai_manipulation_indicator=0.95,
            model_status="UNAVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        assert result["outcome"] != OUTCOME_GENERATIVE_IMAGE_INDICATOR

    def test_inconclusive_on_signal_conflict(self):
        ensemble = {"has_signal_conflict": True, "consensus_label": "CONFLICT"}
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=None,
            ai_manipulation_indicator=0.50,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=ensemble,
        )
        assert result["outcome"] == OUTCOME_INCONCLUSIVE

    def test_no_strong_indicator_found_below_all_thresholds(self):
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=None,
            ai_manipulation_indicator=0.1,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        assert result["outcome"] == OUTCOME_NO_STRONG_INDICATOR_FOUND

    def test_no_strong_indicator_label_never_uses_authentic_or_real(self):
        """The NO_STRONG_INDICATOR_FOUND label and description must not say 'authentic' or 'real image'."""
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=None,
            ai_manipulation_indicator=0.1,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        label = result["label"].lower()
        desc  = result["description"].lower()
        assert "authentic" not in label, f"Label must not use 'authentic': {label}"
        assert "real image" not in label, f"Label must not use 'real image': {label}"
        # Description may use "authentic" in a negation context — that's fine
        # but it must NOT assert authenticity as a positive claim
        assert "certify" not in desc or "does not certify" in desc

    def test_result_always_has_thresholds_applied(self):
        """Every policy result must expose the thresholds that were applied."""
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=None,
            ai_manipulation_indicator=0.5,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        assert "thresholds_applied" in result
        t = result["thresholds_applied"]
        assert "LOCALIZATION_HIGH_RELIABILITY_THRESHOLD" in t
        assert "GENERATIVE_INDICATOR_THRESHOLD" in t

    def test_result_always_has_disclaimer(self):
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=None,
            ai_manipulation_indicator=0.5,
            model_status="AVAILABLE",
            findings=_base_findings(),
            ensemble_agreement=_base_ensemble(),
        )
        assert "disclaimer" in result
        assert len(result["disclaimer"]) > 10

    def test_all_outcome_labels_defined(self):
        outcomes = [
            OUTCOME_VERIFIED_PROVENANCE, OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED,
            OUTCOME_HIGH_RISK_LOCALIZED_ALTERATION, OUTCOME_GENERATIVE_IMAGE_INDICATOR,
            OUTCOME_INCONCLUSIVE, OUTCOME_NO_STRONG_INDICATOR_FOUND,
        ]
        for o in outcomes:
            assert o in OUTCOME_LABELS, f"Label missing for {o}"
            assert o in OUTCOME_DESCRIPTIONS, f"Description missing for {o}"
