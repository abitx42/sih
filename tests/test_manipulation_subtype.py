"""
Tests for RiskEngine manipulation subtype classification.
"""
import pytest
from app.core.risk_engine import RiskEngine


def _subtype(taxonomy, findings=None, indicator=None, model_status="AVAILABLE", score=0.0):
    return RiskEngine.classify_manipulation_subtype(
        forensic_taxonomy=taxonomy,
        findings=findings or [],
        ai_manipulation_indicator=indicator,
        model_status=model_status,
        forensic_anomaly_score=score
    )


def test_authentic_taxonomy_returns_no_manipulation():
    assert _subtype("LIKELY_AUTHENTIC") == "NO_MANIPULATION_DETECTED"


def test_inconclusive_taxonomy_returns_inconclusive():
    assert _subtype("ANALYSIS_INCONCLUSIVE") == "INCONCLUSIVE"


def test_ai_generated_returns_ai_generated():
    assert _subtype("LIKELY_AI_GENERATED", indicator=0.92) == "AI_GENERATED"


def test_face_inpainting_subtype():
    findings = [
        {"category": "LOCALIZED_MANIPULATION", "severity": "HIGH",
         "signal_name": "Inpainting detected in facial region",
         "explanation": "synthetic object near face eyewear added"},
    ]
    result = _subtype("LIKELY_AI_ASSISTED_MANIPULATION", findings=findings, indicator=0.82, score=70.0)
    assert result == "FACE_REGION_INPAINTING"


def test_face_swap_subtype():
    findings = [
        {"category": "AI_MODEL", "severity": "HIGH",
         "signal_name": "Facial deepfake",
         "explanation": "face region shows manipulation"},
    ]
    result = _subtype("LIKELY_AI_ASSISTED_MANIPULATION", findings=findings, indicator=0.88, score=65.0)
    assert result == "FACE_SWAP"


def test_image_splice_subtype():
    findings = [
        {"category": "LOCALIZED_MANIPULATION", "severity": "HIGH",
         "signal_name": "Image splicing artifact",
         "explanation": "splice boundary detected between regions"},
    ]
    result = _subtype("LIKELY_TRADITIONAL_MANIPULATION", findings=findings, indicator=0.55, score=60.0)
    assert result == "IMAGE_SPLICE"


def test_software_edit_subtype():
    findings = [
        {"category": "METADATA", "severity": "MEDIUM",
         "signal_name": "Post-processing editing suite tag",
         "explanation": "Adobe Photoshop 2024 software marker found"},
    ]
    result = _subtype("LIKELY_TRADITIONAL_MANIPULATION", findings=findings, indicator=0.40, score=50.0)
    assert result == "TRADITIONAL_EDIT"


def test_localized_manipulation_fallback():
    findings = [
        {"category": "LOCALIZED_MANIPULATION", "severity": "MEDIUM",
         "signal_name": "Patch anomaly",
         "explanation": "elevated ELA in patch region"},
    ]
    result = _subtype("LIKELY_AI_ASSISTED_MANIPULATION", findings=findings, indicator=0.60, score=45.0)
    assert result == "AI_ASSISTED_EDIT"


def test_ml_unavailable_does_not_trigger_face_swap():
    """Face swap requires ML to be available AND high confidence."""
    findings = [
        {"category": "METADATA", "severity": "LOW",
         "signal_name": "Facial metadata tag",
         "explanation": "face metadata tag present"},
    ]
    result = _subtype("LIKELY_TRADITIONAL_MANIPULATION", findings=findings, indicator=None, model_status="ANALYSIS_UNAVAILABLE", score=55.0)
    # Should not be FACE_SWAP because ML is unavailable
    assert result != "FACE_SWAP"
