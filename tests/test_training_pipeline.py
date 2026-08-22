"""
tests/test_training_pipeline.py
Tests for Phase 5: LoRA Fine-Tuning Pipeline & Model Checkpoint Versioning.
"""
import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.training_pipeline import LoRATrainingPipeline

client = TestClient(app)


def test_list_model_versions_endpoint():
    """Verify list model versions returns at least the baseline model."""
    res = client.get("/api/training/versions")
    assert res.status_code == 200
    data = res.json()
    assert "total_versions" in data
    assert "versions" in data
    assert len(data["versions"]) >= 1
    baseline = [v for v in data["versions"] if "baseline" in v["version_id"] or v["is_active"] == 1]
    assert len(baseline) >= 1


def test_trigger_and_poll_lora_training():
    """Verify triggering LoRA training and monitoring status until completion."""
    # 1. Trigger training
    trigger_res = client.post("/api/training/trigger", json={
        "epochs": 3,
        "learning_rate": 0.0002,
        "batch_size": 8,
        "triggered_by": "Test Suite Examiner"
    })
    assert trigger_res.status_code == 200
    t_data = trigger_res.json()
    assert t_data["success"] is True
    assert "job_id" in t_data
    assert "version_id" in t_data
    version_id = t_data["version_id"]

    # 2. Poll status
    time.sleep(1.5)
    status_res = client.get("/api/training/status")
    assert status_res.status_code == 200
    s_data = status_res.json()
    assert "status" in s_data
    assert "current_epoch" in s_data
    assert "val_accuracy" in s_data

    # Wait for completion (3 epochs * 0.4s = ~1.2s)
    for _ in range(10):
        if not client.get("/api/training/status").json()["is_running"]:
            break
        time.sleep(0.3)

    final_status = client.get("/api/training/status").json()
    assert final_status["status"] == "COMPLETED"
    assert final_status["val_accuracy"] >= 80.0

    # 3. Check version is now listed in database
    v_res = client.get("/api/training/versions")
    assert v_res.status_code == 200
    all_versions = v_res.json()["versions"]
    created_ver = [v for v in all_versions if v["version_id"] == version_id]
    assert len(created_ver) == 1
    assert created_ver[0]["is_active"] == 1


def test_rollback_model_version_endpoint():
    """Verify rolling back to a previous model checkpoint."""
    # 1. Get existing versions
    v_res = client.get("/api/training/versions")
    versions = v_res.json()["versions"]
    assert len(versions) >= 1
    target_id = versions[-1]["version_id"]

    # 2. Rollback to target version
    rb_res = client.post(f"/api/training/rollback/{target_id}")
    assert rb_res.status_code == 200
    rb_data = rb_res.json()
    assert rb_data["success"] is True
    assert rb_data["version_id"] == target_id

    # 3. Verify target is now active
    v_res2 = client.get("/api/training/versions")
    active_v = [v for v in v_res2.json()["versions"] if v["is_active"] == 1]
    assert len(active_v) == 1
    assert active_v[0]["version_id"] == target_id


def test_rollback_invalid_version():
    """Verify 404 on invalid version ID."""
    res = client.post("/api/training/rollback/nonexistent-version-999")
    assert res.status_code == 404
