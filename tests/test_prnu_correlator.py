"""
tests/test_prnu_correlator.py
=============================
Comprehensive unit tests for Multi-Exhibit Camera PRNU Cross-Correlator.
"""
from pathlib import Path
from PIL import Image
from app.config import EVIDENCE_DIR
from app.core.prnu_correlator import PRNUCorrelator


def test_prnu_sensor_noise_extraction():
    """Verify sensor noise extraction produces standardized 512x512 array."""
    img1 = Image.new("RGB", (256, 256), color=(120, 140, 160))
    p1 = EVIDENCE_DIR / "test_sensor_a.jpg"
    img1.save(p1, format="JPEG")

    try:
        noise1 = PRNUCorrelator.extract_sensor_noise(p1)
        assert noise1 is not None
        assert noise1.shape == (512, 512)
    finally:
        if p1.exists():
            p1.unlink()


def test_prnu_correlate_exhibits_flow(evidence_factory):
    """Verify pairwise PRNU cross-correlation between two seeded exhibits."""
    ev_a = "EV-PRNU-TEST-A"
    ev_b = "EV-PRNU-TEST-B"

    # Create test image files on disk
    img_a = Image.new("RGB", (128, 128), color=(100, 150, 200))
    img_b = Image.new("RGB", (128, 128), color=(100, 150, 200))
    path_a = EVIDENCE_DIR / f"{ev_a}_test.jpg"
    path_b = EVIDENCE_DIR / f"{ev_b}_test.jpg"
    img_a.save(path_a, format="JPEG")
    img_b.save(path_b, format="JPEG")

    evidence_factory(
        evidence_id=ev_a,
        filename="test_a.jpg",
        stored_filename=f"{ev_a}_test.jpg",
        modality="IMAGE",
        status="COMPLETED"
    )
    evidence_factory(
        evidence_id=ev_b,
        filename="test_b.jpg",
        stored_filename=f"{ev_b}_test.jpg",
        modality="IMAGE",
        status="COMPLETED"
    )

    try:
        result = PRNUCorrelator.correlate_exhibits(ev_a, ev_b)
        assert result is not None
        assert result["evidence_id_a"] == ev_a
        assert result["evidence_id_b"] == ev_b
        assert "correlation_coefficient" in result
        assert "sensor_match_verdict" in result
        assert result["version"] == PRNUCorrelator.VERSION
    finally:
        if path_a.exists():
            path_a.unlink()
        if path_b.exists():
            path_b.unlink()
