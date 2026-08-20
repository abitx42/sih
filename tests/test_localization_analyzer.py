"""
tests/test_localization_analyzer.py
=====================================
Tests for LocalizationAnalyzer — multi-signal CPU localization engine.
All tests use synthetic PIL images (no real model weights required).
"""
import io
import hashlib
import pytest
from pathlib import Path
from PIL import Image
import numpy as np


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_image(w=256, h=256, color=(128, 128, 128)) -> Image.Image:
    return Image.new("RGB", (w, h), color)


def _make_patched_image(w=256, h=256) -> Image.Image:
    """Image with a bright synthetic patch (simulates localized alteration signal)."""
    img = Image.new("RGB", (w, h), (100, 100, 100))
    arr = np.array(img)
    # Inject a bright high-contrast patch in upper-right quadrant
    arr[20:80, 160:220] = [240, 240, 240]
    arr[20:80, 160:220:2] = [10, 10, 10]  # alternating noise
    return Image.fromarray(arr.astype(np.uint8))


def _save_tmp(img: Image.Image, tmp_path: Path, name: str = "test.jpg") -> Path:
    p = tmp_path / name
    img.save(p, "JPEG", quality=85)
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestLocalizationAnalyzerContract:
    def test_returns_valid_contract_keys(self, tmp_path):
        from app.analyzers.localization_analyzer import LocalizationAnalyzer
        img = _make_image()
        p = _save_tmp(img, tmp_path)
        result = LocalizationAnalyzer().analyze(p, "EV-TEST-001")
        required_keys = {
            "localization_status", "global_integrity_score",
            "manipulation_mask_path", "reliability_map_path",
            "localized_regions", "model_name", "model_version",
            "model_limitations", "error_detail",
        }
        assert required_keys.issubset(set(result.keys())), f"Missing keys: {required_keys - set(result.keys())}"

    def test_localization_status_is_valid_enum(self, tmp_path):
        from app.analyzers.localization_analyzer import (
            LocalizationAnalyzer,
            LOCALIZATION_STATUS_AVAILABLE, LOCALIZATION_STATUS_UNAVAILABLE,
            LOCALIZATION_STATUS_INCONCLUSIVE, LOCALIZATION_STATUS_ERROR,
        )
        img = _make_image()
        p = _save_tmp(img, tmp_path)
        result = LocalizationAnalyzer().analyze(p, "EV-TEST-002")
        valid_statuses = {
            LOCALIZATION_STATUS_AVAILABLE, LOCALIZATION_STATUS_UNAVAILABLE,
            LOCALIZATION_STATUS_INCONCLUSIVE, LOCALIZATION_STATUS_ERROR,
        }
        assert result["localization_status"] in valid_statuses

    def test_global_integrity_score_in_range_or_none(self, tmp_path):
        from app.analyzers.localization_analyzer import LocalizationAnalyzer
        img = _make_image()
        p = _save_tmp(img, tmp_path)
        result = LocalizationAnalyzer().analyze(p, "EV-TEST-003")
        score = result["global_integrity_score"]
        if score is not None:
            assert 0.0 <= score <= 1.0, f"Score out of range: {score}"

    def test_localized_regions_is_list(self, tmp_path):
        from app.analyzers.localization_analyzer import LocalizationAnalyzer
        img = _make_image()
        p = _save_tmp(img, tmp_path)
        result = LocalizationAnalyzer().analyze(p, "EV-TEST-004")
        assert isinstance(result["localized_regions"], list)

    def test_model_name_and_version_present(self, tmp_path):
        from app.analyzers.localization_analyzer import LocalizationAnalyzer, MODEL_NAME, MODEL_VERSION
        img = _make_image()
        p = _save_tmp(img, tmp_path)
        result = LocalizationAnalyzer().analyze(p, "EV-TEST-005")
        assert result["model_name"] == MODEL_NAME
        assert result["model_version"] == MODEL_VERSION

    def test_reliability_cap_does_not_exceed_0_85(self, tmp_path):
        """Reliability per region must be capped at 0.85 to prevent false certainty."""
        from app.analyzers.localization_analyzer import LocalizationAnalyzer
        img = _make_patched_image()
        p = _save_tmp(img, tmp_path, "patched.jpg")
        result = LocalizationAnalyzer().analyze(p, "EV-TEST-006")
        for region in result.get("localized_regions", []):
            assert region["reliability"] <= 0.85, (
                f"Region reliability {region['reliability']} exceeds cap of 0.85"
            )

    def test_neutral_description_does_not_claim_method(self, tmp_path):
        """Neutral descriptions must not claim the specific tool or method of alteration."""
        from app.analyzers.localization_analyzer import LocalizationAnalyzer
        img = _make_patched_image()
        p = _save_tmp(img, tmp_path, "patched2.jpg")
        result = LocalizationAnalyzer().analyze(p, "EV-TEST-007")
        forbidden_phrases = ["photoshop", "ai generated", "deepfake", "confirmed fake", "proven"]
        for region in result.get("localized_regions", []):
            desc = region.get("neutral_description", "").lower()
            for phrase in forbidden_phrases:
                assert phrase not in desc, f"Neutral description contains forbidden phrase '{phrase}': {desc}"
            # Must say method is undetermined
            assert "undetermined" in desc, f"Neutral description should state method is undetermined: {desc}"

    def test_unavailable_on_tiny_image(self, tmp_path):
        """Images smaller than 64x64 must return UNAVAILABLE."""
        from app.analyzers.localization_analyzer import LocalizationAnalyzer, LOCALIZATION_STATUS_UNAVAILABLE
        img = Image.new("RGB", (32, 32), (128, 128, 128))
        p = tmp_path / "tiny.jpg"
        img.save(p, "JPEG")
        result = LocalizationAnalyzer().analyze(p, "EV-TEST-008")
        assert result["localization_status"] == LOCALIZATION_STATUS_UNAVAILABLE

    def test_deterministic_on_same_input(self, tmp_path):
        """Running localization twice on the same file should produce the same status and score."""
        from app.analyzers.localization_analyzer import LocalizationAnalyzer
        img = _make_image()
        p = _save_tmp(img, tmp_path)
        la = LocalizationAnalyzer()
        r1 = la.analyze(p, "EV-DET-001")
        r2 = la.analyze(p, "EV-DET-002")
        assert r1["localization_status"] == r2["localization_status"]
        if r1["global_integrity_score"] is not None and r2["global_integrity_score"] is not None:
            assert abs(r1["global_integrity_score"] - r2["global_integrity_score"]) < 0.01
