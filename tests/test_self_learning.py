"""
tests/test_self_learning.py
Tests for Phase 4: Self-Learning Feedback Loop, Active Learning Queue & Dataset Manifests.
"""
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.core.self_learning import SelfLearningEngine

client = TestClient(app)


def _create_sample_image(color=(140, 90, 210)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (256, 256), color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_learning_stats_endpoint():
    """Verify stats endpoint returns valid dataset counts and readiness metrics."""
    res = client.get("/api/learning/stats")
    assert res.status_code == 200
    data = res.json()
    assert "total_samples" in data
    assert "ai_generated_count" in data
    assert "authentic_real_count" in data
    assert "readiness_percentage" in data
    assert "retrain_status" in data


def test_active_learning_queue_endpoint():
    """Verify active learning queue returns items with uncertainty scores."""
    res = client.get("/api/learning/queue?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert "queue_count" in data
    assert "items" in data
    assert isinstance(data["items"], list)


def test_review_submission_catalogs_training_sample():
    """Verify submitting an investigator review automatically stores confirmed training sample."""
    # 1. Ingest evidence
    img_bytes = _create_sample_image(color=(50, 180, 120))
    files = {"file": ("demo_learning_sample.jpg", img_bytes, "image/jpeg")}
    data = {"case_id": "CASE-2026-001", "uploaded_by": "Test Investigator"}
    upload_res = client.post("/api/evidence/upload", data=data, files=files)
    assert upload_res.status_code in (200, 202)
    ev_id = upload_res.json()["evidence_id"]

    # 2. Submit investigator review
    rev_res = client.post(f"/api/reviews/{ev_id}", json={
        "verdict": "AGREE",
        "notes": "Verified authentic camera baseline.",
        "reviewer_name": "Senior Forensic Analyst"
    })
    assert rev_res.status_code == 200

    # 3. Verify sample recorded in stats
    stats_res = client.get("/api/learning/stats")
    assert stats_res.status_code == 200
    assert stats_res.json()["total_samples"] >= 1


def test_confirm_label_direct_endpoint():
    """Verify /api/learning/confirm-label endpoint directly catalogs ground truth."""
    img_bytes = _create_sample_image(color=(220, 40, 40))
    files = {"file": ("demo_uncertain_ai.jpg", img_bytes, "image/jpeg")}
    data = {"case_id": "CASE-2026-001", "uploaded_by": "Test Investigator"}
    upload_res = client.post("/api/evidence/upload", data=data, files=files)
    assert upload_res.status_code in (200, 202)
    ev_id = upload_res.json()["evidence_id"]

    # Confirm ground truth label
    confirm_res = client.post("/api/learning/confirm-label", json={
        "evidence_id": ev_id,
        "confirmed_label": "AI_GENERATED",
        "reviewer_name": "Special Agent Miller"
    })
    assert confirm_res.status_code == 200
    c_data = confirm_res.json()
    assert c_data["success"] is True
    assert c_data["sample"]["confirmed_label"] == "AI_GENERATED"


def test_export_training_manifest_endpoint():
    """Verify export-manifest produces PyTorch / HuggingFace formatted manifest."""
    res = client.get("/api/learning/export-manifest")
    assert res.status_code == 200
    data = res.json()
    assert "format" in data
    assert "classes" in data
    assert "total_samples" in data
    assert "samples" in data
    assert data["total_samples"] >= 1
