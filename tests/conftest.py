"""
tests/conftest.py
=================
Centralized Pytest fixtures for Truth Lens test suite.
"""
import io
import json
import pytest
from datetime import datetime, timezone
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db, init_db
from app.core.auth import create_access_token


@pytest.fixture(scope="session", autouse=True)
def ensure_database():
    """Ensures database schema and default case are initialized."""
    init_db()


@pytest.fixture
def client():
    """Reusable FastAPI TestClient."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Generates valid JWT Authorization headers for test investigator."""
    token = create_access_token(
        user_id="USR-TEST-INVESTIGATOR",
        email="tester@truthlens.local",
        name="Test Examiner",
        role="INVESTIGATOR"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_image_bytes():
    """Returns in-memory JPEG byte stream for upload tests."""
    img = Image.new("RGB", (100, 100), color=(73, 109, 137))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def evidence_factory():
    """Factory fixture for inserting valid evidence test records with automatic teardown."""
    created_ids = []

    def _create(
        evidence_id: str,
        filename: str = "test.jpg",
        stored_filename: str = "test.jpg",
        modality: str = "IMAGE",
        mime_type: str = "image/jpeg",
        case_id: str = "CASE-2026-001",
        status: str = "COMPLETED"
    ):
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO cases (case_id, title, description, lead_investigator, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (case_id, "Test Case", "Auto-created for test", "Test Lead", now, "ACTIVE"))
            conn.execute("""
                INSERT OR REPLACE INTO evidence (
                    evidence_id, case_id, original_filename, stored_filename,
                    modality, mime_type, file_size_bytes, sha256_hash, sha512_hash,
                    md5_hash, uploaded_by, uploaded_at, status, pipeline_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                evidence_id, case_id, filename, stored_filename,
                modality, mime_type, 1024, "mock_sha256_" + evidence_id,
                "mock_sha512_" + evidence_id, "mock_md5_" + evidence_id,
                "Test Investigator", now, status, status
            ))
        created_ids.append(evidence_id)
        return evidence_id

    yield _create

    # Teardown
    if created_ids:
        with get_db() as conn:
            for eid in created_ids:
                conn.execute("DELETE FROM findings WHERE evidence_id = ?", (eid,))
                conn.execute("DELETE FROM forensic_results WHERE evidence_id = ?", (eid,))
                conn.execute("DELETE FROM chain_of_custody WHERE evidence_id = ?", (eid,))
                conn.execute("DELETE FROM evidence WHERE evidence_id = ?", (eid,))
