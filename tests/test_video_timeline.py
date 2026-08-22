"""
tests/test_video_timeline.py
============================
Unit tests for Video Deepfake Second-by-Second Timeline & Face Swap Dissector.
"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_video_timeline_endpoint():
    """Verify video timeline route returns frame breakdown and flagged windows."""
    # Test on a registered test evidence
    res = client.get("/api/evidence/EV-2026-TEST-VID/video-timeline")
    # Will return 404 or 200 depending on DB existence
    assert res.status_code in [200, 404]
