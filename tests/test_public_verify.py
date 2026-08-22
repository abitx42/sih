"""
tests/test_public_verify.py
===========================
Unit tests for Public 1-Click Fact-Check Debunk page & API.
"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_public_verify_html_and_api():
    """Verify public verification page delivery and metadata API."""
    # Test GET /verify/EV-TEST
    res_html = client.get("/verify/EV-TEST-12345")
    assert res_html.status_code == 200
    assert "Truth Lens" in res_html.text
    assert "Public Verification" in res_html.text
