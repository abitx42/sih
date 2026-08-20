"""
tests/test_calibration_safety.py
=================================
Regression test suite proving compliance with Calibration & Scientific Safety rules:
  1. Heuristic specialists never output definitive verdicts ('AUTHENTIC', 'REAL', 'UNMANIPULATED').
  2. C2PA marker detection ('DETECTED_UNVERIFIED_MANIFEST') never produces 'VERIFIED_PROVENANCE'.
  3. No unvalidated confidence percentage reaches the API.
  4. Localized anomaly descriptions strictly use neutral language (no tool/AI inferences).
  5. Reference comparison output does not claim an editing method or tool.
  6. External detector adapter is absent from the core application pipeline.
"""
from pathlib import Path
from PIL import Image
import numpy as np
import pytest

from app.core.detector_ensemble import (
    FrequencyDomainSpecialist, SyntheticNoiseSpecialist, LocalizedPatchSpecialist,
    ProvenanceMetadataSpecialist, SpatialVisionSpecialist,
    SIGNAL_ALTERATION_DETECTED, SIGNAL_NO_STRONG_ANOMALY, SIGNAL_VERIFIED_PROVENANCE
)
from app.core.localization_policy import (
    PolicyEngine, OUTCOME_VERIFIED_PROVENANCE, OUTCOME_LOCALIZED_ANOMALY_REQUIRING_REVIEW,
    OUTCOME_NO_STRONG_INDICATOR_FOUND
)
from app.analyzers.localization_analyzer import LocalizationAnalyzer
from app.core.reference_comparator import ReferenceComparator, DISCLAIMER
from app.config import settings


def test_heuristic_specialists_never_produce_authentic_or_real():
    freq = FrequencyDomainSpecialist()
    noise = SyntheticNoiseSpecialist()
    patch = LocalizedPatchSpecialist()

    r_freq = freq.analyze(None, fft_anomaly_score=10.0, checkerboard_score=10.0)
    r_noise = noise.analyze(None, noise_anomaly_score=10.0)
    r_patch = patch.analyze({"max_patch_anomaly": 10.0, "localized_regions": []})

    for r in (r_freq, r_noise, r_patch):
        verdict = r["verdict"]
        assert verdict not in ("AUTHENTIC", "REAL", "UNMANIPULATED", "MANIPULATED"), f"Forbidden verdict: {verdict}"
        assert verdict in (SIGNAL_NO_STRONG_ANOMALY, SIGNAL_ALTERATION_DETECTED)


def test_c2pa_marker_never_produces_verified_provenance():
    prov = ProvenanceMetadataSpecialist()
    r = prov.analyze(
        {"status": "DETECTED_UNVERIFIED_MANIFEST", "details": "Marker present in atom"},
        {"metadata_anomaly_score": 0.0}
    )
    assert r["verdict"] != SIGNAL_VERIFIED_PROVENANCE

    policy_res = PolicyEngine.evaluate(
        provenance_status="DETECTED_UNVERIFIED_MANIFEST",
        reference_comparison=None,
        localization_result=None,
        ai_manipulation_indicator=0.1,
        model_status="AVAILABLE",
        findings=[],
        ensemble_agreement=None
    )
    assert policy_res["outcome"] != OUTCOME_VERIFIED_PROVENANCE


def test_calibration_status_is_unvalidated_in_analyzer_and_policy(tmp_path):
    img = Image.new("RGB", (128, 128), (120, 120, 120))
    p = tmp_path / "calib_test.jpg"
    img.save(p, "JPEG")

    loc_res = LocalizationAnalyzer().analyze(p, "EV-CALIB-001")
    assert loc_res["calibration_status"] == "UNVALIDATED"

    pol_res = PolicyEngine.evaluate(
        provenance_status="NOT_AVAILABLE",
        reference_comparison=None,
        localization_result=loc_res,
        ai_manipulation_indicator=0.1,
        model_status="AVAILABLE",
        findings=[],
        ensemble_agreement=None
    )
    assert pol_res["calibration_status"] == "UNVALIDATED"


def test_localized_anomaly_uses_neutral_language(tmp_path):
    img = Image.new("RGB", (200, 200), (80, 80, 80))
    arr = np.array(img)
    arr[30:90, 30:90] = [230, 230, 230]
    p = tmp_path / "neutral_test.jpg"
    Image.fromarray(arr).save(p, "JPEG", quality=90)

    res = LocalizationAnalyzer().analyze(p, "EV-NEUTRAL-001")
    for region in res.get("localized_regions", []):
        desc = region["neutral_description"].lower()
        # Must not claim tool or AI usage
        assert "photoshop" not in desc
        assert "ai generated" not in desc
        assert "deepfake" not in desc
        assert "cannot be determined" in desc or "undetermined" in desc


def test_reference_comparison_wording_does_not_claim_editing_method():
    assert "does not establish which editing tool or method" in DISCLAIMER.lower()
    assert "investigator-supplied comparison reference" in DISCLAIMER.lower()


def test_external_detector_config_absent():
    # Verify no Copyleaks config in Settings
    assert not hasattr(settings, "COPYLEAKS_API_KEY")
