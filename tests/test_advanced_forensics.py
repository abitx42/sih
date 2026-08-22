"""
tests/test_advanced_forensics.py
================================
Unit tests for PRNU Sensor Ballistics, Prompt Inversion Engine,
and 3-Agent Courtroom Debate.
"""
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.config import EVIDENCE_DIR
from app.core.prnu_ballistics import PRNUBallisticsEngine
from app.core.prompt_inverter import PromptInversionEngine
from app.core.courtroom_debate import CourtroomDebateEngine

client = TestClient(app)


def test_prnu_ballistics_engine():
    """Verify PRNU sensor noise fingerprint extraction."""
    test_img = Image.new("RGB", (256, 256), color=(100, 150, 200))
    test_path = EVIDENCE_DIR / "test_prnu_sample.jpg"
    test_img.save(test_path, format="JPEG")

    res = PRNUBallisticsEngine.analyze_prnu(test_path, "TEST-EV-PRNU")
    assert "pce_score" in res
    assert "prnu_ai_indicator" in res
    assert "prnu_verdict" in res
    assert res["prnu_artifact_url"] is not None

    if test_path.exists():
        test_path.unlink()


def test_prompt_inversion_engine():
    """Verify reverse-engineered prompt synthesis."""
    test_img = Image.new("RGB", (300, 300), color=(40, 50, 80))
    test_path = EVIDENCE_DIR / "test_prompt_inv.jpg"
    test_img.save(test_path, format="JPEG")

    res = PromptInversionEngine.invert_prompt(test_path, {"ai_manipulation_indicator": 0.95}, "TEST-EV-PINV")
    assert "reconstructed_positive_prompt" in res
    assert "inferred_negative_prompt" in res
    assert "threat_assessment" in res
    assert res["threat_assessment"]["threat_level"] == "HIGH"
    assert "style_modifiers" in res
    assert len(res["style_modifiers"]) > 0

    if test_path.exists():
        test_path.unlink()


def test_courtroom_debate_engine():
    """Verify 3-agent courtroom debate synthesis."""
    mock_fr = {
        "forensic_risk_score": 94.5,
        "risk_category": "HIGH RISK",
        "ai_manipulation_indicator": 0.96,
        "sha256_hash": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
    }
    debate = CourtroomDebateEngine.conduct_debate("TEST-EV-DEBATE", "suspect_image.jpg", mock_fr)
    assert "prosecutor" in debate
    assert "defense" in debate
    assert "magistrate" in debate
    assert len(debate["prosecutor"]["counts"]) >= 2
    assert "SYNTHETIC" in debate["magistrate"]["ruling_title"]
    assert "INADMISSIBLE" in debate["magistrate"]["admissibility_status"]
