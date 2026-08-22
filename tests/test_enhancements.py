"""
tests/test_enhancements.py
Tests for Disposable Email Blocking, 6-digit OTP Verification, Feedback Submissions, and Guest Quotas.
"""
import io
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.auth import validate_email_domain, generate_verification_code

client = TestClient(app)


def test_disposable_email_domain_blocking():
    """Verify disposable/temp email domains are blocked and popular domains allowed."""
    # Disposable domains -> Must fail
    for blocked_email in [
        "user@mailinator.com",
        "hacker@10minutemail.com",
        "temp@guerrillamail.com",
        "spam@throwawaymail.com",
        "bad@sharklasers.com",
        "test@yopmail.com"
    ]:
        valid, reason = validate_email_domain(blocked_email)
        assert valid is False
        assert "blocked" in reason.lower() or "disposable" in reason.lower()

    # Legitimate domains -> Must pass
    for good_email in [
        "investigator@gmail.com",
        "officer@yahoo.com",
        "agent@outlook.com",
        "analyst@icloud.com",
        "forensics@agency.gov.in",
        "researcher@university.edu"
    ]:
        valid, _ = validate_email_domain(good_email)
        assert valid is True


def test_registration_with_disposable_email_fails():
    """Registration endpoint must reject disposable email with 400 Bad Request."""
    res = client.post("/api/auth/register", json={
        "name": "Temp User",
        "email": "tester@mailinator.com",
        "password": "secretpassword123",
        "data_consent": True
    })
    assert res.status_code == 400
    assert "disposable" in res.json()["detail"].lower() or "blocked" in res.json()["detail"].lower()


def test_email_otp_verification_flow():
    """Verify signup -> 6-digit OTP generation -> verification -> account verified."""
    email = f"officer_{int(__import__('time').time())}@gmail.com"

    # 1. Register with real email
    reg_res = client.post("/api/auth/register", json={
        "name": "Insp. Ananya Patel",
        "email": email,
        "password": "securepassword99",
        "data_consent": True
    })
    assert reg_res.status_code == 200
    data = reg_res.json()
    assert data["success"] is True
    assert "verification_code_demo" in data
    code = data["verification_code_demo"]
    assert len(code) == 6

    # 2. Verify with wrong code -> Should fail
    wrong_res = client.post("/api/auth/verify-email", json={
        "email": email,
        "code": "000000"
    })
    assert wrong_res.status_code == 400

    # 3. Verify with correct code -> Should succeed
    ok_res = client.post("/api/auth/verify-email", json={
        "email": email,
        "code": code
    })
    assert ok_res.status_code == 200
    assert ok_res.json()["success"] is True


def test_feedback_submission_endpoint():
    """Verify /api/feedback accepts bug reports and observations with optional attachments."""
    # Text feedback
    res = client.post("/api/feedback", data={
        "name": "Forensic Auditor",
        "email": "auditor@agency.gov",
        "is_anonymous": "false",
        "category": "BUG_REPORT",
        "description": "Observed slight UI misalignment on mobile screens when inspecting difference map.",
        "evidence_id": "EV-2026-TEST-01",
        "rating": "4"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "feedback_id" in data

    # Anonymous feedback with file attachment
    fake_file = io.BytesIO(b"PNG_FAKE_SCREENSHOT_DATA")
    res_anon = client.post(
        "/api/feedback",
        data={
            "is_anonymous": "true",
            "category": "ACCURACY_OBSERVATION",
            "description": "Model detected 95% AI on an authentic DSLR sample with heavy bokeh.",
            "rating": "5"
        },
        files={"attachment": ("screenshot.png", fake_file, "image/png")}
    )
    assert res_anon.status_code == 200
    assert res_anon.json()["success"] is True

    # List feedback
    list_res = client.get("/api/feedback")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 2
