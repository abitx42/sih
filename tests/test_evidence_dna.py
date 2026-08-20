"""
Tests for Evidence DNA fingerprint builder and known-file detection.
"""
import pytest
from app.core.evidence_dna import EvidenceDNA


SAMPLE_METRICS = {
    "dimensions": "4032x3024",
    "aspect_ratio": 1.333,
    "exif": {
        "Make": "Apple",
        "Model": "iPhone 15 Pro",
        "Software": "16.5",
        "ColorSpace": 1
    },
    "forensic_anomaly_score": 12.5,
    "ensemble_agreement": {
        "total_specialists_evaluated": 5,
        "manipulated_count": 1,
        "authentic_count": 4
    },
    "risk_components": {
        "manipulation_subtype": "NO_MANIPULATION_DETECTED"
    }
}


def test_dna_builds_basic_fields():
    dna = EvidenceDNA.build_dna(
        evidence_id="EV-TEST-001",
        sha256_hash="a" * 64,
        original_filename="photo.jpg",
        modality="IMAGE",
        file_size_bytes=2048000,
        raw_metrics=SAMPLE_METRICS,
        provenance_result={"status": "NOT_AVAILABLE"}
    )
    assert dna["evidence_id"] == "EV-TEST-001"
    assert dna["camera"] == "Apple iPhone 15 Pro"
    assert dna["dimensions"] == "4032x3024"
    assert dna["color_space"] == "sRGB"
    assert dna["metadata_field_count"] == 4
    assert dna["provenance_status"] == "NOT_AVAILABLE"
    assert dna["ai_signals_flagged"] == 1
    assert dna["ai_signals_total"] == 5
    assert len(dna["dna_fingerprint"]) == 64  # sha256 hex


def test_dna_fingerprint_is_deterministic():
    """Same input should produce the same DNA fingerprint."""
    dna1 = EvidenceDNA.build_dna("EV-001", "a" * 64, "file.jpg", "IMAGE", 1024, SAMPLE_METRICS)
    dna2 = EvidenceDNA.build_dna("EV-001", "a" * 64, "file.jpg", "IMAGE", 1024, SAMPLE_METRICS)
    assert dna1["dna_fingerprint"] == dna2["dna_fingerprint"]


def test_dna_fingerprint_changes_on_different_sha256():
    """Different SHA-256 → different DNA fingerprint."""
    dna1 = EvidenceDNA.build_dna("EV-001", "a" * 64, "file.jpg", "IMAGE", 1024, SAMPLE_METRICS)
    dna2 = EvidenceDNA.build_dna("EV-001", "b" * 64, "file.jpg", "IMAGE", 1024, SAMPLE_METRICS)
    assert dna1["dna_fingerprint"] != dna2["dna_fingerprint"]


def test_dna_camera_fallback_no_exif():
    dna = EvidenceDNA.build_dna("EV-002", "c" * 64, "unknown.png", "IMAGE", 512000, {})
    assert dna["camera"] == "Not Identified"
    assert dna["metadata_field_count"] == 0


def test_dna_compression_extension_fallback():
    dna = EvidenceDNA.build_dna("EV-003", "d" * 64, "evidence.PNG", "IMAGE", 1000, {})
    assert dna["compression"] == "PNG"


def test_dna_provenance_status_captured():
    dna = EvidenceDNA.build_dna(
        "EV-004", "e" * 64, "signed.jpg", "IMAGE", 3000000,
        SAMPLE_METRICS,
        provenance_result={"status": "VERIFIED"}
    )
    assert dna["provenance_status"] == "VERIFIED"


def test_dna_known_file_returns_none_on_first_upload(tmp_path, monkeypatch):
    """Known-file check returns None when no duplicate exists."""
    from unittest.mock import patch, MagicMock
    # get_db is a local import inside check_known_file, so patch at the source module
    with patch("app.database.get_db") as mock_db:
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn
        result = EvidenceDNA.check_known_file("some_fp_hash", "EV-001")
        assert result is None


