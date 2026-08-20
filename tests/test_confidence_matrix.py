"""
Tests for Forensic Confidence Matrix builder.
"""
import pytest
from app.core.confidence_matrix import ConfidenceMatrix

GREEN = "GREEN"
RED = "RED"
AMBER = "AMBER"
GREY = "GREY"


def _build(
    risk_score=20.0,
    risk_category="LOW RISK",
    taxonomy="LIKELY_AUTHENTIC",
    ensemble=None,
    provenance="NOT_AVAILABLE",
    findings=None,
    raw=None
):
    return ConfidenceMatrix.build(
        forensic_risk_score=risk_score,
        risk_category=risk_category,
        forensic_taxonomy=taxonomy,
        ensemble_agreement=ensemble or {},
        provenance_status=provenance,
        findings=findings or [],
        raw_metrics=raw or {}
    )


def test_matrix_returns_six_axes():
    result = _build()
    assert len(result["axes"]) == 6
    labels = [a["label"] for a in result["axes"]]
    assert "AI Models" in labels
    assert "Pixel Forensics" in labels
    assert "Signal Agreement" in labels


def test_authentic_scenario_all_green():
    raw = {
        "forensic_anomaly_score": 10.0,
        "risk_components": {"ai_manipulation_risk": 15.0, "metadata_risk": 5.0, "model_status": "AVAILABLE"}
    }
    ens = {
        "total_specialists_evaluated": 5,
        "manipulated_count": 0,
        "authentic_count": 5,
        "agreement_percentage": 100.0,
        "consensus_verdict": "AUTHENTIC_BASELINE_CONSENSUS",
        "has_signal_conflict": False
    }
    result = _build(risk_score=10.0, risk_category="LOW RISK", taxonomy="LIKELY_AUTHENTIC",
                    ensemble=ens, provenance="NOT_AVAILABLE", raw=raw)
    axes = {a["label"]: a for a in result["axes"]}

    assert axes["AI Models"]["authentic_signal"] == GREEN
    assert axes["Pixel Forensics"]["authentic_signal"] == GREEN
    assert axes["Signal Agreement"]["authentic_signal"] == GREEN
    assert result["summary"]["manipulation_signals"] == 0


def test_high_manipulation_scenario_shows_red():
    raw = {
        "forensic_anomaly_score": 78.0,
        "risk_components": {"ai_manipulation_risk": 85.0, "metadata_risk": 60.0, "model_status": "AVAILABLE"}
    }
    ens = {
        "total_specialists_evaluated": 5,
        "manipulated_count": 4,
        "authentic_count": 1,
        "agreement_percentage": 80.0,
        "consensus_verdict": "STRONG_MANIPULATION_CONSENSUS",
        "has_signal_conflict": False
    }
    findings = [{"category": "LOCALIZED_MANIPULATION", "severity": "HIGH", "signal_name": "Inpainting detected", "explanation": "", "location_ref": "Face"}]
    result = _build(risk_score=82.0, risk_category="HIGH RISK", taxonomy="LIKELY_AI_ASSISTED_MANIPULATION",
                    ensemble=ens, provenance="NOT_AVAILABLE", findings=findings, raw=raw)
    axes = {a["label"]: a for a in result["axes"]}

    assert axes["AI Models"]["manipulated_signal"] == RED
    assert axes["Pixel Forensics"]["manipulated_signal"] == RED
    assert axes["Signal Agreement"]["manipulated_signal"] == RED
    assert result["summary"]["manipulation_signals"] >= 3


def test_signal_conflict_produces_amber():
    ens = {
        "has_signal_conflict": True,
        "total_specialists_evaluated": 6,
        "manipulated_count": 3,
        "authentic_count": 3,
        "agreement_percentage": 50.0,
        "consensus_verdict": "CONFLICTING_SIGNALS"
    }
    result = _build(risk_score=50.0, risk_category="REVIEW REQUIRED", taxonomy="ANALYSIS_INCONCLUSIVE",
                    ensemble=ens)
    axes = {a["label"]: a for a in result["axes"]}
    assert result["summary"]["has_conflict"] is True
    # Signal Agreement should be AMBER on conflict
    assert axes["Signal Agreement"]["authentic_signal"] == AMBER
    assert axes["Signal Agreement"]["manipulated_signal"] == AMBER


def test_c2pa_verified_provenance():
    result = _build(provenance="VERIFIED")
    axes = {a["label"]: a for a in result["axes"]}
    assert axes["Provenance"]["authentic_signal"] == GREEN
    assert axes["Provenance"]["manipulated_signal"] == GREY


def test_c2pa_invalid_provenance():
    result = _build(provenance="INVALID")
    axes = {a["label"]: a for a in result["axes"]}
    assert axes["Provenance"]["manipulated_signal"] == RED


def test_ml_unavailable_shows_amber_ai_axis():
    raw = {"risk_components": {"model_status": "ANALYSIS UNAVAILABLE", "ai_manipulation_risk": None}}
    result = _build(raw=raw)
    axes = {a["label"]: a for a in result["axes"]}
    assert axes["AI Models"]["authentic_signal"] == AMBER
    assert axes["AI Models"]["manipulated_signal"] == AMBER
