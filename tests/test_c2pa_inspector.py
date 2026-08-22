"""
tests/test_c2pa_inspector.py
============================
Unit tests for C2PA Content Credentials & Cryptographic Manifest Inspector.
"""
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.config import EVIDENCE_DIR
from app.core.c2pa_manifest_inspector import C2PAManifestInspector

client = TestClient(app)


def test_c2pa_manifest_inspector_unverified_and_generative():
    """Verify C2PA manifest extraction on synthetic and direct camera buffers."""
    test_file = EVIDENCE_DIR / "test_c2pa_sample.jpg"
    
    # Write a file containing simulated JUMBF / C2PA marker
    with open(test_file, "wb") as f:
        f.write(b"\xFF\xD8\xFF\xE1" + b"ContentCredentials c2pa.claim_generator=Adobe_Photoshop_2025 c2pa.created trainedAlgorithmicMedia" + b"\xFF\xD9")

    res = C2PAManifestInspector.inspect_file(test_file, "TEST-EV-C2PA")
    assert res["has_c2pa_manifest"] is True
    assert "Adobe" in res["claim_generator"]
    assert res["digital_source_type"] == "SYNTHETIC_GENERATIVE_AI"
    assert len(res["action_assertions"]) > 0

    if test_file.exists():
        test_file.unlink()
