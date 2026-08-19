from app.core.risk_engine import RiskEngine

def test_low_risk_scenario():
    score, category, conf, comps = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_score=0.05,
        forensic_signal_anomalies=10.0,
        metadata_anomaly_score=5.0,
        provenance_status="VERIFIED",
        findings=[]
    )
    assert score <= 30.0
    assert category == "LOW RISK"
    assert conf >= 0.85

def test_high_risk_scenario():
    score, category, conf, comps = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_score=0.92,
        forensic_signal_anomalies=85.0,
        metadata_anomaly_score=75.0,
        provenance_status="NOT_AVAILABLE",
        findings=[{"severity": "CRITICAL"}]
    )
    assert score >= 70.0
    assert category == "HIGH RISK"

def test_integrity_mismatch_override():
    score, category, conf, comps = RiskEngine.calculate_risk(
        integrity_status="MISMATCH",
        ai_manipulation_score=0.10,
        forensic_signal_anomalies=10.0,
        metadata_anomaly_score=10.0,
        provenance_status="NOT_AVAILABLE",
        findings=[{"severity": "CRITICAL"}]
    )
    assert score >= 70.0
    assert category == "HIGH RISK"
