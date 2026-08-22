"""
tests/test_cloud_vision_gateway.py
Tests for Multi-Cloud Zero-Cost Vision Gateway, Rate-Limit Circuit Breakers, and Consensus Aggregation.
"""
import io
import time
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.core.cloud_vision_ensemble import MultiCloudVisionGateway, ProviderCircuitBreaker

client = TestClient(app)


def _create_test_image() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (256, 256), color=(200, 100, 80))
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_cloud_providers_status_endpoint():
    """Verify status endpoint returns live provider info and circuit breaker stats."""
    res = client.get("/api/cloud-models/status")
    assert res.status_code == 200
    data = res.json()
    assert "total_providers" in data
    assert "active_healthy_count" in data
    assert "providers" in data
    assert data["total_providers"] >= 5

    # Pollinations zero-key provider must always be ready
    pollinations = [p for p in data["providers"] if "Pollinations" in p["name"]]
    assert len(pollinations) == 1
    assert pollinations[0]["is_zero_key"] is True


def test_circuit_breaker_rate_limiting_and_recovery():
    """Verify 429 rate limit triggers COOLDOWN and auto-recovers after expiration."""
    cb = ProviderCircuitBreaker("TestCloudProvider", is_zero_key=True)
    assert cb.is_available() is True
    assert cb.status == "HEALTHY"

    # Simulate 429 rate limit with 1 second cooldown
    cb.report_rate_limit(cooldown_seconds=1.0, err_msg="Rate limit reached (429)")
    assert cb.status == "COOLDOWN"
    assert cb.is_available() is False
    info = cb.get_info()
    assert info["cooldown_remaining_sec"] > 0

    # Wait for cooldown expiration
    time.sleep(1.2)
    assert cb.is_available() is True
    assert cb.status == "HEALTHY"


def test_multi_cloud_cross_check_endpoint():
    """Verify /api/cloud-models/cross-check/{id} executes cross-model consensus."""
    img_bytes = _create_test_image()
    files = {"file": ("demo_cloud_check.jpg", img_bytes, "image/jpeg")}
    data = {"case_id": "CASE-2026-001", "uploaded_by": "Test Investigator"}
    upload_res = client.post("/api/evidence/upload", data=data, files=files)
    assert upload_res.status_code in (200, 202)
    ev_id = upload_res.json()["evidence_id"]

    # Trigger cloud cross-check
    cc_res = client.post(f"/api/cloud-models/cross-check/{ev_id}")
    assert cc_res.status_code == 200
    cc_data = cc_res.json()
    assert cc_data["success"] is True
    assert "cross_check" in cc_data
    cc = cc_data["cross_check"]
    assert "consensus_verdict" in cc
    assert "consensus_confidence" in cc
    assert "cloud_results" in cc
    assert len(cc["cloud_results"]) >= 1
