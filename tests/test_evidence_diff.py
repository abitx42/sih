"""
Tests for Evidence Diff Engine.
"""
import io
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.core.evidence_diff import EvidenceDiffEngine


def _make_rgb_image(color=(100, 100, 100), size=(64, 64)):
    from PIL import Image
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf


def test_identical_images_show_no_change(tmp_path):
    from PIL import Image
    img = Image.new("RGB", (64, 64), (120, 120, 120))
    p = tmp_path / "same.jpg"
    img.save(str(p), format="JPEG", quality=95)

    ev = {"original_filename": "same.jpg", "modality": "IMAGE", "file_size_bytes": p.stat().st_size, "sha256_hash": "a" * 64}
    result = EvidenceDiffEngine.compare("EV-A", "EV-B", p, p, ev, ev, forensic_dir=tmp_path)

    assert result["pixel_diff"] is not None
    assert result["pixel_diff"]["pct_pixels_changed"] < 5.0  # near-identical (JPEG rounding)


def test_different_images_show_significant_change(tmp_path):
    from PIL import Image
    img_a = Image.new("RGB", (64, 64), (0, 0, 0))
    img_b = Image.new("RGB", (64, 64), (255, 255, 255))
    p_a = tmp_path / "black.jpg"
    p_b = tmp_path / "white.jpg"
    img_a.save(str(p_a), format="JPEG", quality=95)
    img_b.save(str(p_b), format="JPEG", quality=95)

    ev_a = {"original_filename": "black.jpg", "modality": "IMAGE", "file_size_bytes": p_a.stat().st_size, "sha256_hash": "a" * 64}
    ev_b = {"original_filename": "white.jpg", "modality": "IMAGE", "file_size_bytes": p_b.stat().st_size, "sha256_hash": "b" * 64}

    result = EvidenceDiffEngine.compare("EV-A", "EV-B", p_a, p_b, ev_a, ev_b, forensic_dir=tmp_path)

    assert result["pixel_diff"]["mean_absolute_difference"] > 50.0
    assert result["pixel_diff"]["pct_pixels_changed"] > 90.0
    assert result["pixel_diff"]["significant_change"] is True


def test_diff_saves_heatmap(tmp_path):
    from PIL import Image
    img_a = Image.new("RGB", (64, 64), (0, 0, 0))
    img_b = Image.new("RGB", (64, 64), (200, 200, 200))
    p_a = tmp_path / "dark.jpg"
    p_b = tmp_path / "light.jpg"
    img_a.save(str(p_a), format="JPEG", quality=95)
    img_b.save(str(p_b), format="JPEG", quality=95)

    ev = {"original_filename": "img.jpg", "modality": "IMAGE", "file_size_bytes": 1024, "sha256_hash": "a" * 64}
    result = EvidenceDiffEngine.compare("EV-A", "EV-B", p_a, p_b, ev, ev, forensic_dir=tmp_path)

    assert result["diff_heatmap_url"] is not None
    heatmap_path = tmp_path / "diff_EV-A_EV-B.png"
    assert heatmap_path.exists()


def test_non_image_modality_skips_pixel_diff(tmp_path):
    p = tmp_path / "audio.wav"
    p.write_bytes(b"RIFF" + b"\x00" * 100)

    ev = {"original_filename": "audio.wav", "modality": "AUDIO", "file_size_bytes": 104, "sha256_hash": "c" * 64}
    result = EvidenceDiffEngine.compare("EV-A", "EV-B", p, p, ev, ev, forensic_dir=None)

    assert result["pixel_diff"] is None
    assert "only available for IMAGE" in result["summary"]


def test_metadata_diff_detects_changes():
    ev_a = {"original_filename": "a.jpg", "modality": "IMAGE", "file_size_bytes": 1000, "sha256_hash": "a" * 64}
    ev_b = {"original_filename": "b.jpg", "modality": "IMAGE", "file_size_bytes": 5000, "sha256_hash": "b" * 64}
    diffs = EvidenceDiffEngine._diff_metadata(ev_a, ev_b, None, None)
    changed = [d for d in diffs if d["changed"]]
    assert any(d["field"] == "File Size (bytes)" for d in changed)
    assert any(d["field"] == "SHA-256" for d in changed)


def test_geometry_diff_detected(tmp_path):
    from PIL import Image
    img_a = Image.new("RGB", (100, 100), (50, 50, 50))
    img_b = Image.new("RGB", (150, 150), (60, 60, 60))
    p_a = tmp_path / "small.jpg"
    p_b = tmp_path / "large.jpg"
    img_a.save(str(p_a), format="JPEG", quality=95)
    img_b.save(str(p_b), format="JPEG", quality=95)

    ev = {"original_filename": "img.jpg", "modality": "IMAGE", "file_size_bytes": 1024, "sha256_hash": "x" * 64}
    result = EvidenceDiffEngine.compare("EV-A", "EV-B", p_a, p_b, ev, ev, forensic_dir=None)

    assert result["geometry_diff"]["resize_detected"] is True
    assert result["geometry_diff"]["dimensions_match"] is False


def test_change_region_detection():
    """Smoke test — change regions returned for high-diff image array."""
    h, w = 64, 64
    # Simulate a high-diff in the upper-right quadrant
    diff = np.zeros((h, w, 3), dtype=np.int32)
    diff[0:32, 32:64] = 200  # Upper right filled with high diff
    regions = EvidenceDiffEngine._detect_change_regions(diff, w, h)
    # Should detect at least one region in upper right area
    assert len(regions) >= 1
