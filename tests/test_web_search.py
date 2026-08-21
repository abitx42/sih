"""
tests/test_web_search.py
Tests for Phase 2: Internet Cross-Check, Reverse Image Search & News Fact-Check Research.
"""
import io
import uuid
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.analyzers.internet_search_analyzer import InternetSearchAnalyzer, MATCH_EXACT, MATCH_PARTIAL, MATCH_NONE
from app.core.provenance_web import WebProvenanceEngine

client = TestClient(app)


def _create_sample_image(width=300, height=300, color=(100, 150, 200)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_multiscale_phash_computation():
    """Verify multi-scale pHash extracts global + 5 quadrant/crop hashes."""
    analyzer = InternetSearchAnalyzer()
    img = Image.new("RGB", (400, 400), color=(120, 180, 240))
    hashes = analyzer._compute_multi_scale_hashes(img)

    assert "global_phash" in hashes
    assert "top_left_phash" in hashes
    assert "top_right_phash" in hashes
    assert "bottom_left_phash" in hashes
    assert "bottom_right_phash" in hashes
    assert "center_phash" in hashes


def test_provenance_article_consensus_synthesis():
    """Verify multi-source news consensus calculates rates and summary properly."""
    sample_match = {
        "title": "Press Briefing Graphic",
        "source": "Reuters",
        "match_type": "EXACT_DUPLICATE"
    }
    res = WebProvenanceEngine.research_articles(
        evidence_id="EV-TEST-001",
        best_match=sample_match,
        all_matches=[sample_match]
    )

    assert "articles" in res
    assert len(res["articles"]) > 0
    assert "consensus_verdict" in res
    assert "manipulation_reporting_rate_pct" in res
    assert res["consensus_confidence"] >= 50.0


def test_web_search_api_endpoints():
    """Verify web search POST and GET endpoints for an ingested exhibit."""
    # 1. Ingest an evidence image
    img_bytes = _create_sample_image(200, 200, color=(80, 120, 160))
    files = {"file": ("demo_viral_altered.jpg", img_bytes, "image/jpeg")}
    data = {"case_id": "CASE-2026-001", "uploaded_by": "Test Investigator"}
    upload_res = client.post("/api/evidence/upload", data=data, files=files)
    assert upload_res.status_code in (200, 202)
    ev_id = upload_res.json()["evidence_id"]

    # 2. Trigger web cross-check search
    search_res = client.post(f"/api/evidence/{ev_id}/web-search")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["success"] is True
    assert "search_results" in search_data
    assert "provenance_articles" in search_data

    # 3. Retrieve stored search results via GET
    get_res = client.get(f"/api/evidence/{ev_id}/web-search")
    assert get_res.status_code == 200
    retrieved = get_res.json()
    assert retrieved["evidence_id"] == ev_id
    assert "match_status" in retrieved
    assert "match_confidence" in retrieved
    assert "provenance_articles" in retrieved


def test_web_search_nonexistent_evidence():
    """Verify 404 for invalid evidence ID."""
    res = client.post("/api/evidence/EV-NONEXISTENT-999/web-search")
    assert res.status_code == 404
