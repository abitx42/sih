from app.core.risk_engine import RiskEngine

def test_low_risk_scenario_with_ml_available():
    score, category, conf, comps = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=0.04,
        model_status="AVAILABLE",
        forensic_anomaly_score=8.0,
        metadata_anomaly_score=5.0,
        provenance_status="VERIFIED",
        findings=[]
    )
    assert score <= 30.0
    assert category == "LOW RISK"
    assert conf >= 0.85
    assert comps["ai_manipulation_risk"] == 4.0

def test_high_risk_scenario_with_ml_available():
    score, category, conf, comps = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=0.94,
        model_status="AVAILABLE",
        forensic_anomaly_score=82.0,
        metadata_anomaly_score=75.0,
        provenance_status="NOT_AVAILABLE",
        findings=[{"severity": "CRITICAL"}]
    )
    assert score >= 70.0
    assert category == "HIGH RISK"
    assert comps["ai_manipulation_risk"] == 94.0

def test_ml_unavailable_defaults_to_review_required():
    """
    When ML classification is ANALYSIS UNAVAILABLE and no extreme findings exist,
    the platform must default to REVIEW REQUIRED and not assume LOW RISK.
    """
    score, category, conf, comps = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=None,
        model_status="ANALYSIS UNAVAILABLE",
        forensic_anomaly_score=10.0,
        metadata_anomaly_score=5.0,
        provenance_status="VERIFIED",
        findings=[]
    )
    assert category == "REVIEW REQUIRED"
    assert score >= 35.0
    assert comps["ai_manipulation_risk"] is None
    assert comps["model_status"] == "ANALYSIS UNAVAILABLE"

def test_ml_unavailable_elevates_to_high_risk_on_critical_findings():
    """
    When ML is unavailable but independent high-severity heuristic findings exist,
    the platform correctly flags HIGH RISK.
    """
    score, category, conf, comps = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=None,
        model_status="ANALYSIS UNAVAILABLE",
        forensic_anomaly_score=88.0,
        metadata_anomaly_score=80.0,
        provenance_status="NOT_AVAILABLE",
        findings=[{"severity": "CRITICAL"}, {"severity": "HIGH"}]
    )
    assert category == "HIGH RISK"
    assert score >= 70.0

def test_integrity_mismatch_overrides_to_high_risk():
    """
    A bitstream hash mismatch indicates on-disk file alteration,
    triggering high forensic risk regardless of ML score.
    """
    score, category, conf, comps = RiskEngine.calculate_risk(
        integrity_status="MISMATCH",
        ai_manipulation_indicator=0.02,
        model_status="AVAILABLE",
        forensic_anomaly_score=5.0,
        metadata_anomaly_score=5.0,
        provenance_status="VERIFIED",
        findings=[]
    )
    assert score == 100.0
    assert category == "HIGH RISK"
    assert comps["integrity_risk"] == 100.0
