import pytest
import io
import json
from unittest.mock import patch, MagicMock
from PIL import Image

from app.core.detector_ensemble import (
    SpatialVisionSpecialist,
    FrequencyDomainSpecialist,
    SyntheticNoiseSpecialist,
    LocalizedPatchSpecialist,
    ProvenanceMetadataSpecialist,
    ExternalDetectorAdapter,
    EnsembleAgreementEngine
)
from app.core.risk_engine import RiskEngine
from app.config import settings

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
        assert res["verdict"] == "MANIPULATED"
        assert res["indicator"] == 0.88
        assert res["status"] == "COMPLETED"

    # Mock HFDetector unavailable
    with patch("app.core.detector_ensemble._hf_detector.predict") as mock_pred:
        mock_pred.return_value = {
            "model_status": "ANALYSIS UNAVAILABLE",
            "ai_manipulation_indicator": None,
            "model_confidence": None
        }
        res = specialist.analyze("dummy.jpg")
        assert res["verdict"] == "UNAVAILABLE"
        assert res["status"] == "ANALYSIS UNAVAILABLE"

def test_frequency_domain_specialist():
    specialist = FrequencyDomainSpecialist()
    # High frequency / checkerboard anomalies
    res_high = specialist.analyze(None, fft_anomaly_score=75.0, checkerboard_score=80.0)
    assert res_high["verdict"] == "MANIPULATED"
    assert res_high["score"] > 60.0

    # Clean radial baseline
    res_clean = specialist.analyze(None, fft_anomaly_score=15.0, checkerboard_score=20.0)
    assert res_clean["verdict"] == "AUTHENTIC"
    assert res_clean["score"] < 35.0

def test_synthetic_noise_specialist():
    specialist = SyntheticNoiseSpecialist()
    res_noise = specialist.analyze(None, noise_anomaly_score=68.0)
    assert res_noise["verdict"] == "MANIPULATED"

    res_clean = specialist.analyze(None, noise_anomaly_score=22.0)
    assert res_clean["verdict"] == "AUTHENTIC"

def test_localized_patch_specialist():
    specialist = LocalizedPatchSpecialist()
    # Localized ROI present
    res_roi = specialist.analyze({
        "max_patch_anomaly": 78.5,
        "localized_regions": [
            {"region_id": "ROI-1", "semantic_label": "Eyewear / Facial Region", "anomaly_score": 78.5}
        ]
    })
    assert res_roi["verdict"] == "MANIPULATED"
    assert res_roi["regions_count"] == 1

    # Uniform baseline
    res_uniform = specialist.analyze({
        "max_patch_anomaly": 18.0,
        "localized_regions": []
    })
    assert res_uniform["verdict"] == "AUTHENTIC"
    assert res_uniform["regions_count"] == 0

def test_provenance_metadata_specialist():
    specialist = ProvenanceMetadataSpecialist()

    # C2PA verified
    res_prov = specialist.analyze({"status": "VERIFIED", "details": "Signed by Canon"}, {"metadata_anomaly_score": 0.0})
    assert res_prov["verdict"] == "AUTHENTIC"

    # Editing software detected
    res_edit = specialist.analyze({"status": "NOT_AVAILABLE"}, {"metadata_anomaly_score": 60.0, "editing_software_detected": True, "software": "Adobe Photoshop 2026"})
    assert res_edit["verdict"] == "MANIPULATED"

def test_external_detector_adapter_unconfigured():
    adapter = ExternalDetectorAdapter()
    with patch.object(settings, "COPYLEAKS_API_KEY", ""):
        res = adapter.analyze("dummy.jpg")
        assert res["status"] == "NOT_CONFIGURED"
        assert res["verdict"] == "SKIPPED"
        assert "not set" in res["details"]

def test_ensemble_agreement_engine_consensus():
    specialists = [
        {"specialist_type": "SPATIAL_VISION", "status": "COMPLETED", "verdict": "MANIPULATED", "indicator": 0.85},
        {"specialist_type": "FREQUENCY_DOMAIN", "status": "COMPLETED", "verdict": "MANIPULATED", "indicator": 0.75},
        {"specialist_type": "SYNTHETIC_TEXTURE", "status": "COMPLETED", "verdict": "MANIPULATED", "indicator": 0.70},
        {"specialist_type": "LOCAL_PATCH", "status": "COMPLETED", "verdict": "MANIPULATED", "indicator": 0.80},
        {"specialist_type": "PROVENANCE_METADATA", "status": "COMPLETED", "verdict": "MANIPULATED", "indicator": 0.60},
        {"specialist_type": "EXTERNAL_DETECTOR", "status": "NOT_CONFIGURED", "verdict": "SKIPPED", "indicator": None}
    ]

    consensus = EnsembleAgreementEngine.evaluate_consensus(specialists)
    assert consensus["active_specialists_count"] == 5
    assert consensus["manipulated_signals_count"] == 5
    assert consensus["authentic_signals_count"] == 0
    assert consensus["consensus_verdict"] == "STRONG_MANIPULATION_CONSENSUS"
    assert consensus["has_signal_conflict"] is False

def test_ensemble_agreement_engine_signal_conflict():
    # Spatial ViT says MANIPULATED with high confidence (0.85), but noise and metadata say AUTHENTIC
    specialists = [
        {"specialist_type": "SPATIAL_VISION", "status": "COMPLETED", "verdict": "MANIPULATED", "indicator": 0.85},
        {"specialist_type": "SYNTHETIC_TEXTURE", "status": "COMPLETED", "verdict": "AUTHENTIC", "indicator": 0.15},
        {"specialist_type": "PROVENANCE_METADATA", "status": "COMPLETED", "verdict": "AUTHENTIC", "indicator": 0.10},
        {"specialist_type": "LOCAL_PATCH", "status": "COMPLETED", "verdict": "AUTHENTIC", "indicator": 0.15}
    ]

    consensus = EnsembleAgreementEngine.evaluate_consensus(specialists)
    assert consensus["has_signal_conflict"] is True
    assert consensus["consensus_verdict"] == "CONFLICTING_SIGNALS"
    assert "PRNU sensor noise" in consensus["conflict_description"]

    # RiskEngine evaluation on signal conflict
    score, cat, conf, comp = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=0.85,
        model_status="AVAILABLE",
        forensic_anomaly_score=20.0,
        metadata_anomaly_score=10.0,
        provenance_status="NOT_AVAILABLE",
        findings=[],
        ensemble_agreement=consensus
    )
    assert cat == "REVIEW REQUIRED"
    assert comp["forensic_taxonomy"] == "ANALYSIS_INCONCLUSIVE"
    assert comp["has_signal_conflict"] is True
