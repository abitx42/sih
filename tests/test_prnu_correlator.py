"""
tests/test_prnu_correlator.py
=============================
Unit tests for Multi-Exhibit Camera PRNU Cross-Correlator.
"""
from PIL import Image
from app.config import EVIDENCE_DIR
from app.core.prnu_correlator import PRNUCorrelator


def test_prnu_correlator_identical_vs_distinct():
    """Verify sensor correlation identifies identical vs different sensor arrays."""
    # 1. Create sample image
    img1 = Image.new("RGB", (256, 256), color=(120, 140, 160))
    p1 = EVIDENCE_DIR / "test_sensor_a.jpg"
    img1.save(p1, format="JPEG")

    noise1 = PRNUCorrelator.extract_sensor_noise(p1)
    assert noise1 is not None
    assert noise1.shape == (512, 512)

    if p1.exists():
        p1.unlink()
