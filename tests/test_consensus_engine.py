import pytest
from app.core.consensus_engine import ConsensusEngine

def test_all_signals_agree_ai():
    signals = {
        'hf_ensemble': 0.8,
        'sightengine': 0.9,
        'prnu_ai_indicator': 0.85,
        'ela_anomaly': 80,
    }
    result = ConsensusEngine.compute_consensus(signals)
    assert result['consensus_verdict'] == "CONSENSUS_AI_GENERATED"
    assert result['consensus_confidence'] == "HIGH"
    assert result['has_conflict'] is False
    assert result['ai_votes'] == 4

def test_all_signals_agree_authentic():
    signals = {
        'hf_ensemble': 0.1,
        'sightengine': 0.2,
        'prnu_ai_indicator': 0.15,
        'ela_anomaly': 20,
    }
    result = ConsensusEngine.compute_consensus(signals)
    assert result['consensus_verdict'] == "CONSENSUS_LIKELY_AUTHENTIC"
    assert result['consensus_confidence'] == "HIGH"
    assert result['has_conflict'] is False
    assert result['authentic_votes'] == 4

def test_conflicting_signals():
    signals = {
        'hf_ensemble': 0.9,
        'sightengine': 0.8,
        'prnu_ai_indicator': 0.1,
        'ela_anomaly': 10,
    }
    result = ConsensusEngine.compute_consensus(signals)
    assert result['consensus_verdict'] == "CONFLICTING_SIGNALS_REVIEW_REQUIRED"
    assert result['consensus_confidence'] == "LOW"
    assert result['has_conflict'] is True

def test_no_signals():
    signals = {}
    result = ConsensusEngine.compute_consensus(signals)
    assert result['consensus_verdict'] == "NO_SIGNALS_AVAILABLE"
    assert result['total_signals'] == 0

def test_partial_signals():
    signals = {
        'hf_ensemble': 0.8,
        'sightengine': 0.9,
    }
    result = ConsensusEngine.compute_consensus(signals)
    assert result['consensus_verdict'] == "LEANING_AI_GENERATED"
    assert result['consensus_confidence'] == "LOW"
    assert result['total_signals'] == 2

def test_ela_normalization():
    signals = {
        'ela_anomaly': 85.0
    }
    result = ConsensusEngine.compute_consensus(signals)
    assert result['signal_breakdown']['ela_anomaly'] == 0.85

def test_c2pa_verified():
    signals = {
        'c2pa_verified': True
    }
    result = ConsensusEngine.compute_consensus(signals)
    assert result['signal_breakdown']['c2pa_verified'] == 0.05
    assert result['consensus_verdict'] == "LEANING_AUTHENTIC"
