"""
tests/test_turing_gauntlet.py
=============================
Unit tests for The Turing Gauntlet engine and API routes.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.turing_gauntlet import TuringGauntletEngine, CURATED_CHALLENGES

client = TestClient(app)


def test_turing_gauntlet_engine_challenge():
    """Verify engine generates valid challenges."""
    ch = TuringGauntletEngine.get_challenge()
    assert "challenge_id" in ch
    assert "image_url" in ch
    assert "difficulty" in ch
    assert ch["difficulty"] in ("EASY", "MEDIUM", "HARD", "NIGHTMARE")


def test_turing_gauntlet_evaluate_submission():
    """Verify evaluation logic and active learning feedback."""
    res = TuringGauntletEngine.evaluate_submission(
        challenge_id="GAUNTLET-001",
        user_guess="AI",
        response_time_ms=1200,
        investigator_name="Test Investigator"
    )
    assert res["is_correct"] is True
    assert res["ground_truth"] == "AI GENERATED"
    assert "artifacts_detected" in res
    assert len(res["artifacts_detected"]) > 0
    assert res["truth_lens_ai_confidence"] >= 95.0


def test_turing_gauntlet_api_endpoints():
    """Verify HTTP API endpoints for gauntlet challenge and submission."""
    # 1. Fetch challenge
    r1 = client.get("/api/gauntlet/challenge")
    assert r1.status_code == 200
    c_data = r1.json()
    assert "challenge_id" in c_data

    # 2. Submit guess
    r2 = client.post("/api/gauntlet/submit", json={
        "challenge_id": c_data["challenge_id"],
        "user_guess": "AI",
        "response_time_ms": 1500,
        "investigator_name": "Senior Forensic Analyst"
    })
    assert r2.status_code == 200
    res_data = r2.json()
    assert "is_correct" in res_data
    assert "forensic_explanation" in res_data
    assert "stats" in res_data

    # 3. Fetch stats
    r3 = client.get("/api/gauntlet/stats")
    assert r3.status_code == 200
    stats = r3.json()
    assert "truth_lens_accuracy_pct" in stats
    assert stats["truth_lens_accuracy_pct"] >= 90.0

    # 4. Fetch sample image
    r4 = client.get(f"/api/gauntlet/sample/{c_data['challenge_id']}.jpg")
    assert r4.status_code == 200
    assert r4.headers["content-type"] in ("image/jpeg", "image/jpg")
