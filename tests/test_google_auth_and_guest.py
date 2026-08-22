"""
tests/test_google_auth_and_guest.py
Tests for Google OAuth authentication and resilient Guest Mode session handling.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_guest_access_and_me_endpoint_never_404():
    """Verify Guest access generates token and /me endpoint returns guest profile without 404."""
    # 1. Obtain Guest Token
    res = client.post("/api/auth/guest")
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["user"]["is_guest"] is True
    guest_token = data["token"]

    # 2. Query /api/auth/me with guest token
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {guest_token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["is_guest"] is True
    assert me_data["role"] == "GUEST"
    assert "user_id" in me_data


def test_google_authentication_flow():
    """Verify POST /api/auth/google registers or logs in a Google user."""
    test_google_email = "investigator.raj@gmail.com"
    payload = {
        "email": test_google_email,
        "name": "Insp. Raj Malhotra",
        "google_id": "GOOGLE-UID-987654321",
        "avatar_url": "https://lh3.googleusercontent.com/a/default-user"
    }

    res = client.post("/api/auth/google", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "token" in data
    assert data["user"]["email"] == test_google_email
    assert data["user"]["auth_provider"] == "GOOGLE"
    assert data["user"]["email_verified"] is True

    # Check /me with Google token
    google_token = data["token"]
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {google_token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == test_google_email
    assert me_data["is_guest"] is False
