"""
tests/test_auth.py
Tests for the Truth Lens authentication system (Phase 1).
"""
import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_auth_status():
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert "auth_enabled" in res.json()


def test_register_and_login_flow():
    email = f"test_{uuid.uuid4().hex[:6]}@forensics.test"
    # Register
    res = client.post("/api/auth/register", json={
        "name": "Test Investigator", "email": email,
        "password": "securePass123", "data_consent": False,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "token" in data
    assert data["user"]["role"] == "INVESTIGATOR"
    assert data["user"]["tc_accepted"] is False

    # Login
    res2 = client.post("/api/auth/login", json={"email": email, "password": "securePass123"})
    assert res2.status_code == 200
    token = res2.json()["token"]

    # /me
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    # Accept T&C
    res4 = client.post("/api/auth/accept-terms",
        json={"data_consent": True}, headers={"Authorization": f"Bearer {token}"})
    assert res4.status_code == 200
    assert res4.json()["success"] is True


def test_register_duplicate_email():
    email = f"dup_{uuid.uuid4().hex[:6]}@forensics.test"
    payload = {"name": "Agent Smith", "email": email, "password": "test123"}
    assert client.post("/api/auth/register", json=payload).status_code == 200
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_register_weak_password():
    res = client.post("/api/auth/register", json={
        "name": "A", "email": "short@test.com", "password": "abc"
    })
    assert res.status_code == 400


def test_login_wrong_password():
    email = f"wp_{uuid.uuid4().hex[:6]}@forensics.test"
    client.post("/api/auth/register", json={"name": "B", "email": email, "password": "correct123"})
    res = client.post("/api/auth/login", json={"email": email, "password": "wrongpassword"})
    assert res.status_code == 401


def test_guest_access():
    res = client.post("/api/auth/guest")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "token" in data
    assert data["user"]["role"] == "GUEST"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert me.status_code == 200
    assert me.json()["is_guest"] is True


def test_me_without_token():
    assert client.get("/api/auth/me").status_code == 401


def test_me_invalid_token():
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert res.status_code == 401


def test_logout():
    res = client.post("/api/auth/logout")
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_jwt_tampered_signature_rejected():
    """Verify that a forged or altered JWT signature is immediately rejected."""
    # Obtain a valid token first
    res = client.post("/api/auth/guest")
    assert res.status_code == 200
    valid_token = res.json()["token"]

    parts = valid_token.split(".")
    assert len(parts) == 3
    # Tamper with signature
    tampered_token = f"{parts[0]}.{parts[1]}.tampered_signature_payload"

    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert res_me.status_code == 401


def test_jwt_none_algorithm_attack_rejected():
    """Verify algorithm confusion attack with 'none' algorithm is rejected."""
    # Unsigned token header + payload: {"alg": "none"}
    header_b64 = "eyJhbGciOiAibm9uZSIgfQ"
    payload_b64 = "eyJzdWIiOiAiVVNSLVRFU1QiLCAiZW1haWwiOiAiaGFja2VyQHRlc3QubG9jYWwiLCAicm9sZSI6ICJBRU1JTiIsICJleHAiOiA5OTk5OTk5OTk5fQ"
    forged_token = f"{header_b64}.{payload_b64}."

    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged_token}"})
    assert res_me.status_code == 401
