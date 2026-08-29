"""
tests/test_video_timeline.py
============================
Unit tests for Video Deepfake Second-by-Second Timeline & Face Swap Dissector.
"""
import json
from datetime import datetime, timezone
from app.database import get_db


def test_video_timeline_not_found(client):
    """Verify video timeline route returns 404 for nonexistent evidence."""
    res = client.get("/api/evidence/NONEXISTENT-VID-123/video-timeline")
    assert res.status_code == 404


def test_video_timeline_with_seeded_evidence(client, evidence_factory):
    """Verify video timeline route returns frame breakdown and flagged windows for valid evidence."""
    ev_id = "EV-2026-TEST-VID-SEEDED"
    evidence_factory(
        evidence_id=ev_id,
        filename="test_deepfake.mp4",
        stored_filename="test_deepfake.mp4",
        modality="VIDEO",
        mime_type="video/mp4",
        status="COMPLETED"
    )

    raw_metrics = {
        "duration_seconds": 10.0,
        "fps": 30.0,
        "ml_detector": {
            "frame_details": [
                {"frame_index": 0, "timestamp_seconds": 0.0, "ai_manipulation_indicator": 0.15, "is_suspicious": False},
                {"frame_index": 1, "timestamp_seconds": 2.5, "ai_manipulation_indicator": 0.85, "is_suspicious": True},
                {"frame_index": 2, "timestamp_seconds": 5.0, "ai_manipulation_indicator": 0.90, "is_suspicious": True},
                {"frame_index": 3, "timestamp_seconds": 7.5, "ai_manipulation_indicator": 0.20, "is_suspicious": False}
            ]
        }
    }

    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO forensic_results (
                result_id, evidence_id, integrity_status, provenance_status,
                ai_manipulation_score, ai_manipulation_indicator, ai_model_name,
                ai_model_version, model_confidence, model_status, forensic_anomaly_score,
                forensic_risk_score, risk_category, confidence_score, analyzed_at,
                raw_metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"RES-{ev_id}", ev_id, "VERIFIED", "NOT_AVAILABLE",
            88.0, 0.88, "ViT-Video-Ensemble", "1.0.0", 0.94, "AVAILABLE",
            25.0, 88.0, "HIGH RISK", 0.94, now, json.dumps(raw_metrics)
        ))

    res = client.get(f"/api/evidence/{ev_id}/video-timeline")
    assert res.status_code == 200
    data = res.json()
    assert data["evidence_id"] == ev_id
    assert "timeline_frames" in data
    assert len(data["timeline_frames"]) == 4
    assert "flagged_windows" in data
    assert len(data["flagged_windows"]) == 1
    assert data["flagged_windows"][0]["start_sec"] == 2.5
    assert data["flagged_windows"][0]["end_sec"] == 5.0
