"""
tests/test_system_diagnostics.py
================================
Unit and integration tests for SystemDiagnostics and system telemetry endpoints.
"""
from fastapi.testclient import TestClient
from app.main import app
from app.core.system_diagnostics import SystemDiagnostics

client = TestClient(app)


def test_system_diagnostics_unit():
    health = SystemDiagnostics.get_system_health()
    assert isinstance(health, dict)
    assert health["status"] in ["HEALTHY", "DEGRADED"]
    assert "Truth Lens" in health["service"]
    assert "environment" in health
    assert "python_version" in health["environment"]
    assert "compute_device" in health["environment"]
    assert "database" in health
    assert health["database"]["status"] == "HEALTHY"
    assert "latency_ms" in health["database"]
    assert "storage" in health
    assert "free_disk_gb" in health["storage"]
    assert "configured_gateways" in health
    assert isinstance(health["configured_gateways"], dict)


def test_system_info_endpoint():
    response = client.get("/api/system/info")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "service" in data
    assert "environment" in data
    assert "database" in data
    assert "storage" in data
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] >= 0


def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "Truth Lens" in data["service"]
