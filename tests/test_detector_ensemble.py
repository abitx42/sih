import pytest
from unittest.mock import patch

from app.core.detector_ensemble import (
    SpatialVisionSpecialist,
    FrequencyDomainSpecialist,
    SyntheticNoiseSpecialist,
    LocalizedPatchSpecialist,
    ProvenanceMetadataSpecialist,
    EnsembleAgreementEngine,
    SIGNAL_ALTERATION_DETECTED,
    SIGNAL_NO_STRONG_ANOMALY,
    SIGNAL_INCONCLUSIVE,
    SIGNAL_UNAVAILABLE,
    SIGNAL_VERIFIED_PROVENANCE,
)


def test_spatial_vision_specialist():
    specialist = SpatialVisionSpecialist()
    assert specialist.name == "Spatial Vision Classifier (ViT)"
    assert specialist.specialist_type == "SPATIAL_VISION"
    assert specialist.category == "AI_MODEL"

    # Mock HFDetector available with high manipulation indicator
    with patch("app.core.detector_ensemble._hf_detector.predict") as mock_pred:
        mock_pred.return_value = {
            "model_status": "AVAILABLE",
            "ai_manipulation_indicator": 0.88,
            "model_confidence": 0.92,
            "ai_model_name": "test_vit",
            "ai_model_version": "1.0"
        }
        res = specialist.analyze("dummy.jpg")
        assert res["verdict"] == SIGNAL_ALTERATION_DETECTED
        assert res["indicator"] == 0.88
        assert res["status"] == "COMPLETED"
        assert res["calibration_status"] == "UNVALIDATED"

    # Mock HFDetector unavailable
    with patch("app.core.detector_ensemble._hf_detector.predict") as mock_pred:
        mock_pred.return_value = {
            "model_status": "ANALYSIS UNAVAILABLE",
            "ai_manipulation_indicator": None,
            "model_confidence": None
        }
        res = specialist.analyze("dummy.jpg")
        assert res["verdict"] == SIGNAL_UNAVAILABLE
        assert res["status"] == "ANALYSIS UNAVAILABLE"


def test_frequency_domain_specialist_neutral_signals():
    specialist = FrequencyDomainSpecialist()
    # High frequency / checkerboard anomalies
    res_high = specialist.analyze(None, fft_anomaly_score=75.0, checkerboard_score=80.0)
    assert res_high["verdict"] == SIGNAL_ALTERATION_DETECTED
    assert res_high["score"] > 60.0

    # Clean radial baseline
    res_clean = specialist.analyze(None, fft_anomaly_score=15.0, checkerboard_score=20.0)
    assert res_clean["verdict"] == SIGNAL_NO_STRONG_ANOMALY
    assert res_clean["score"] < 35.0


def test_synthetic_noise_specialist_neutral_signals():
    specialist = SyntheticNoiseSpecialist()
    res_noise = specialist.analyze(None, noise_anomaly_score=68.0)
    assert res_noise["verdict"] == SIGNAL_ALTERATION_DETECTED

    res_clean = specialist.analyze(None, noise_anomaly_score=22.0)
    assert res_clean["verdict"] == SIGNAL_NO_STRONG_ANOMALY


def test_localized_patch_specialist_neutral_signals():
    specialist = LocalizedPatchSpecialist()
    # Localized ROI present
    res_roi = specialist.analyze({
        "max_patch_anomaly": 78.5,
        "localized_regions": [
            {"region_id": "ROI-1", "semantic_label": "Eyewear / Facial Region", "anomaly_score": 78.5}
        ]
    })
    assert res_roi["verdict"] == SIGNAL_ALTERATION_DETECTED
    assert res_roi["regions_count"] == 1

    # Uniform baseline
    res_uniform = specialist.analyze({
        "max_patch_anomaly": 18.0,
        "localized_regions": []
    })
    assert res_uniform["verdict"] == SIGNAL_NO_STRONG_ANOMALY
    assert res_uniform["regions_count"] == 0


def test_provenance_metadata_specialist():
    specialist = ProvenanceMetadataSpecialist()

    # Real C2PA cryptographic validation passed
    res_prov = specialist.analyze({"status": "CRYPTOGRAPHIC_VALIDATION_PASSED", "details": "Signed by Trust Root"}, {"metadata_anomaly_score": 0.0})
    assert res_prov["verdict"] == SIGNAL_VERIFIED_PROVENANCE

    # Editing software detected
    res_edit = specialist.analyze({"status": "NOT_AVAILABLE"}, {"metadata_anomaly_score": 60.0, "editing_software_detected": True, "software": "Adobe Photoshop 2026"})
    assert res_edit["verdict"] == SIGNAL_ALTERATION_DETECTED


def test_ensemble_agreement_engine_consensus():
    specialists = [
        {"specialist_type": "SPATIAL_VISION", "status": "COMPLETED", "verdict": SIGNAL_ALTERATION_DETECTED, "indicator": 0.85},
        {"specialist_type": "FREQUENCY_DOMAIN", "status": "COMPLETED", "verdict": SIGNAL_ALTERATION_DETECTED, "indicator": 0.75},
        {"specialist_type": "SYNTHETIC_TEXTURE", "status": "COMPLETED", "verdict": SIGNAL_ALTERATION_DETECTED, "indicator": 0.70},
        {"specialist_type": "LOCAL_PATCH", "status": "COMPLETED", "verdict": SIGNAL_ALTERATION_DETECTED, "indicator": 0.80},
        {"specialist_type": "PROVENANCE_METADATA", "status": "COMPLETED", "verdict": SIGNAL_ALTERATION_DETECTED, "indicator": 0.60},
    ]

    consensus = EnsembleAgreementEngine.evaluate_consensus(specialists)
    assert consensus["active_specialists_count"] == 5
    assert consensus["alteration_signals_count"] == 5
    assert consensus["consensus_verdict"] == "STRONG_ALTERATION_SIGNAL_CONSENSUS"
    assert "Alteration Signal Consensus" in consensus["consensus_label"]
