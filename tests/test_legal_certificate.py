"""
tests/test_legal_certificate.py
===============================
Unit tests for Section 65B / BSA 2023 Electronic Evidence Certificate Generator.
"""
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.config import EVIDENCE_DIR
from app.core.legal_certificate import LegalCertificateGenerator

client = TestClient(app)


def test_legal_certificate_payload_and_pdf():
    """Verify Section 65B certificate payload and PDF compilation."""
    mock_ev = {
        "evidence_id": "TEST-EV-BSA",
        "case_id": "CASE-2026-001",
        "original_filename": "surveillance_still.jpg",
        "file_size_bytes": 102400,
        "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "sha512_hash": "cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e"
    }
    mock_case = {
        "case_id": "CASE-2026-001",
        "title": "Operation CyberShield"
    }
    mock_fr = {
        "forensic_risk_score": 96.5,
        "risk_category": "HIGH RISK",
        "ai_manipulation_indicator": 0.98,
        "raw_metrics_json": '{"pce_score": 8.2, "dire": {"dire_score": 92.0}}'
    }

    # 1. Payload
    payload = LegalCertificateGenerator.create_certificate_payload(mock_ev, mock_case, mock_fr)
    assert payload["certificate_id"].startswith("BSA-65B-")
    assert "Section 63" in payload["statutory_act"]
    assert len(payload["statutory_clauses"]) >= 3
    assert "SYNTHETIC" in payload["forensic_verdict"]["classification"]

    # 2. PDF Generation
    pdf_path = LegalCertificateGenerator.generate_pdf(mock_ev, mock_case, mock_fr)
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 2000  # Non-empty PDF with QR code

    # Cleanup
    if pdf_path.exists():
        pdf_path.unlink()
