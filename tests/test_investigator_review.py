"""
Tests for Investigator Review API endpoint.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _upload_and_complete_evidence():
    """Helper: upload a small image and mark it as COMPLETED for review tests."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (100, 100, 100)).save(buf, format="JPEG")
    buf.seek(0)

    resp = client.post("/api/evidence/upload", data={"case_id": "CASE-REVIEW-TEST", "uploaded_by": "ReviewTester"}, files={"file": ("review_img.jpg", buf, "image/jpeg")})
    assert resp.status_code == 202
    return resp.json()["evidence_id"]


def test_submit_valid_review():
    ev_id = _upload_and_complete_evidence()

    # Force COMPLETED status for test
    from app.database import get_db
    with get_db() as conn:
        conn.execute("UPDATE evidence SET status = 'COMPLETED' WHERE evidence_id = ?", (ev_id,))

    resp = client.post(f"/api/reviews/{ev_id}", json={
        "verdict": "AGREE",
        "notes": "Findings match manual inspection.",
        "reviewer_name": "Senior Examiner"
    })
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["verdict"] == "AGREE"
    assert data["evidence_id"] == ev_id
    assert "review_id" in data
    assert data["reviewer_name"] == "Senior Examiner"


def test_submit_disagree_review():
    ev_id = _upload_and_complete_evidence()
    from app.database import get_db
    with get_db() as conn:
        conn.execute("UPDATE evidence SET status = 'COMPLETED' WHERE evidence_id = ?", (ev_id,))

    resp = client.post(f"/api/reviews/{ev_id}", json={
        "verdict": "DISAGREE",
        "notes": "Manual inspection inconclusive.",
        "reviewer_name": "Examiner B"
    })
    assert resp.status_code in (200, 201)
    assert resp.json()["verdict"] == "DISAGREE"


def test_submit_invalid_verdict_rejected():
    ev_id = _upload_and_complete_evidence()
    from app.database import get_db
    with get_db() as conn:
        conn.execute("UPDATE evidence SET status = 'COMPLETED' WHERE evidence_id = ?", (ev_id,))

    resp = client.post(f"/api/reviews/{ev_id}", json={"verdict": "MAYBE", "reviewer_name": "Tester"})
    assert resp.status_code == 400
    assert "Invalid verdict" in resp.json()["detail"]


def test_review_for_analyzing_evidence_rejected():
    ev_id = _upload_and_complete_evidence()
    # Explicitly force ANALYZING so the review endpoint rejects it
    from app.database import get_db
    with get_db() as conn:
        conn.execute("UPDATE evidence SET status = 'ANALYZING' WHERE evidence_id = ?", (ev_id,))
    resp = client.post(f"/api/reviews/{ev_id}", json={"verdict": "AGREE", "reviewer_name": "Tester"})
    # Should be 400 because analysis not complete yet
    assert resp.status_code == 400



def test_get_review_returns_latest():
    ev_id = _upload_and_complete_evidence()
    from app.database import get_db
    with get_db() as conn:
        conn.execute("UPDATE evidence SET status = 'COMPLETED' WHERE evidence_id = ?", (ev_id,))

    client.post(f"/api/reviews/{ev_id}", json={"verdict": "AGREE", "reviewer_name": "Tester"})
    resp = client.get(f"/api/reviews/{ev_id}")
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "AGREE"


def test_get_review_returns_null_if_no_review():
    ev_id = _upload_and_complete_evidence()
    resp = client.get(f"/api/reviews/{ev_id}")
    assert resp.status_code == 200
    assert resp.json() is None


def test_review_updates_custody_log():
    ev_id = _upload_and_complete_evidence()
    from app.database import get_db
    with get_db() as conn:
        conn.execute("UPDATE evidence SET status = 'COMPLETED' WHERE evidence_id = ?", (ev_id,))

    client.post(f"/api/reviews/{ev_id}", json={"verdict": "NEEDS_FURTHER_EXAMINATION", "reviewer_name": "Forensic Lead"})

    resp = client.get(f"/api/custody?evidence_id={ev_id}")
    assert resp.status_code == 200
    events = resp.json()
    actions = [e["action"] for e in events]
    assert "INVESTIGATOR_REVIEW_SUBMITTED" in actions
