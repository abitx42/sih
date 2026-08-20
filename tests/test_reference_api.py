"""
tests/test_reference_api.py
============================
Tests for the Reference Comparison API endpoints.
"""
import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app
from app.database import get_db

client = TestClient(app)


def _create_test_image_bytes(color=(120, 120, 120), size=(200, 200), fmt="JPEG"):
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def sample_evidence_id():
    """Uploads a test image evidence and ensures it completes analysis."""
    img_bytes = _create_test_image_bytes(color=(100, 150, 200))
    files = {"file": ("test_exhibit.jpg", img_bytes, "image/jpeg")}
    data = {"case_id": "CASE-2026-001", "notes": "Reference comparison test exhibit"}
    
    response = client.post("/api/evidence/upload", files=files, data=data)
    assert response.status_code in (200, 201, 202)
    ev_id = response.json()["evidence_id"]
    
    # Wait or force status to COMPLETED if needed
    with get_db() as conn:
        conn.execute("UPDATE evidence SET status = 'COMPLETED', pipeline_status = 'COMPLETED' WHERE evidence_id = ?", (ev_id,))
    return ev_id


def test_reference_compare_endpoint_success(sample_evidence_id):
    ref_bytes = _create_test_image_bytes(color=(100, 150, 200))
    files = {"reference_original": ("ref_original.jpg", ref_bytes, "image/jpeg")}
    data = {"submitted_by": "Investigator Jones"}
    
    resp = client.post(f"/api/evidence/{sample_evidence_id}/reference-compare", files=files, data=data)
    assert resp.status_code == 200
    res_data = resp.json()
    assert "comparison_status" in res_data
    assert "ssim_score" in res_data
    assert "reference_sha256" in res_data
    assert "disclaimer" in res_data
    assert res_data["evidence_id"] == sample_evidence_id


def test_get_reference_compare_endpoint(sample_evidence_id):
    # First submit comparison
    ref_bytes = _create_test_image_bytes(color=(100, 150, 200))
    files = {"reference_original": ("ref_original.jpg", ref_bytes, "image/jpeg")}
    client.post(f"/api/evidence/{sample_evidence_id}/reference-compare", files=files, data={"submitted_by": "Investigator"})
    
    # Then GET comparison
    resp = client.get(f"/api/evidence/{sample_evidence_id}/reference-compare")
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data is not None
    assert res_data["evidence_id"] == sample_evidence_id
    assert "comparison_status" in res_data


def test_reference_compare_nonexistent_evidence_returns_404():
    ref_bytes = _create_test_image_bytes()
    files = {"reference_original": ("ref.jpg", ref_bytes, "image/jpeg")}
    resp = client.post("/api/evidence/EV-NONEXISTENT/reference-compare", files=files)
    assert resp.status_code == 404


def test_reference_compare_invalid_file_type_rejected(sample_evidence_id):
    files = {"reference_original": ("fake.txt", b"Hello world text data", "text/plain")}
    resp = client.post(f"/api/evidence/{sample_evidence_id}/reference-compare", files=files)
    assert resp.status_code == 400
