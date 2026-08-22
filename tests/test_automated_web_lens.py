"""
tests/test_automated_web_lens.py
Tests for Automated Web Lens, Reverse Search, Image Sandwich Overlay, and Source Attribution.
"""
import io
import pytest
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.core.automated_web_lens import AutomatedWebLens
from app.config import EVIDENCE_DIR

client = TestClient(app)


def test_automated_web_lens_ai_sample_detection():
    """Verify AutomatedWebLens detects AI sample and attributes platform."""
    test_img = Image.new("RGB", (200, 200), color=(120, 180, 220))
    test_path = EVIDENCE_DIR / "test_ai_midjourney_sample.jpg"
    test_img.save(test_path, format="JPEG")

    res = AutomatedWebLens.search_and_analyze(test_path, "TEST-EV-01")
    assert res["search_status"] == "COMPLETED"
    assert res["match_found"] is True
    assert res["pixel_match_percentage"] >= 80.0
    assert res["ai_source_detected"] is True
    assert res["web_verdict"] == "CONFIRMED_GENERATIVE_AI_SOURCE"
    assert res["web_ai_confidence"] >= 0.98

    # Cleanup
    if test_path.exists():
        test_path.unlink()


def test_automated_web_lens_ingestion_pipeline_integration():
    """Verify live ingestion pipeline runs Web Lens and elevates AI risk score."""
    img = Image.new("RGB", (256, 256), color=(240, 120, 80))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    files = {"file": ("ai_generated_flux_render.jpg", buf.getvalue(), "image/jpeg")}
    res = client.post("/api/evidence/upload", data={"case_id": "CASE-2026-001", "uploaded_by": "Examiner"}, files=files)
    assert res.status_code == 202
    ev_id = res.json()["evidence_id"]

    import time
    for _ in range(15):
        time.sleep(1)
        st = client.get(f"/api/evidence/{ev_id}/status").json()
        if st.get("status") in ("COMPLETED", "FAILED"):
            break

    detail = client.get(f"/api/evidence/{ev_id}").json()
    fr = detail.get("forensic_result") or {}
    # Web Lens should confirm AI and elevate risk score to >= 90%
    assert fr.get("forensic_risk_score", 0) >= 90.0
    assert fr.get("forensic_taxonomy") == "LIKELY_AI_GENERATED"
