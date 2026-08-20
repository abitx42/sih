"""
Tests for Adversarial Robustness Stress Tester.
"""
import io
import pytest
from pathlib import Path
from unittest.mock import patch


def _make_test_image(tmp_path, color=(128, 64, 32)):
    from PIL import Image
    img = Image.new("RGB", (64, 64), color)
    p = tmp_path / "test.jpg"
    img.save(str(p), format="JPEG", quality=95)
    return p


def test_robustness_tester_runs_all_transforms(tmp_path):
    from app.core.robustness_tester import RobustnessTester, TRANSFORMS
    p = _make_test_image(tmp_path)
    result = RobustnessTester.run(p, "EV-TEST", "REVIEW REQUIRED", 45.0)

    assert "transforms" in result
    assert result["total_transforms"] == len(TRANSFORMS)
    for t in result["transforms"]:
        assert "key" in t
        assert "verdict" in t
        assert "latency_ms" in t


def test_robustness_tester_returns_robustness_label(tmp_path):
    from app.core.robustness_tester import RobustnessTester
    p = _make_test_image(tmp_path)
    result = RobustnessTester.run(p, "EV-TEST", "REVIEW REQUIRED", 45.0)

    assert result["robustness_label"] in ("HIGH ROBUSTNESS", "MODERATE ROBUSTNESS", "LOW ROBUSTNESS")
    assert 0.0 <= result["robustness_percentage"] <= 100.0


def test_robustness_tester_includes_original_transform(tmp_path):
    from app.core.robustness_tester import RobustnessTester
    p = _make_test_image(tmp_path)
    result = RobustnessTester.run(p, "EV-TEST", "REVIEW REQUIRED", 45.0)

    keys = [t["key"] for t in result["transforms"]]
    assert "original" in keys
    assert "jpeg_90" in keys
    assert "social_media" in keys


def test_robustness_tester_fails_gracefully_on_invalid_file(tmp_path):
    from app.core.robustness_tester import RobustnessTester
    p = tmp_path / "garbage.jpg"
    p.write_bytes(b"not an image at all")
    result = RobustnessTester.run(p, "EV-TEST", "REVIEW REQUIRED", 45.0)
    # Should return an error dict, not raise
    assert "error" in result


def test_fft_score_returns_float(tmp_path):
    from app.core.robustness_tester import RobustnessTester
    import numpy as np
    arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8).astype(np.float32)
    score = RobustnessTester._fft_score(arr)
    assert isinstance(score, float)
    assert 0.0 <= score <= 100.0


def test_noise_score_low_variance_image(tmp_path):
    from app.core.robustness_tester import RobustnessTester
    import numpy as np
    # Flat colour → very low noise variance → should flag as anomalous (synthetic-like)
    arr = np.full((64, 64, 3), 128, dtype=np.float32)
    score = RobustnessTester._noise_score(arr)
    assert score > 0.0
