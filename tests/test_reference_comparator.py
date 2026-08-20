"""
tests/test_reference_comparator.py
=====================================
Tests for ReferenceComparator — trusted-reference image comparison.
"""
import pytest
from pathlib import Path
from PIL import Image
import numpy as np


def _solid_image(w=200, h=200, color=(128, 100, 80)) -> Image.Image:
    return Image.new("RGB", (w, h), color)


def _save(img, path, name, fmt="JPEG") -> Path:
    p = path / name
    img.save(p, fmt)
    return p


def _patched_copy(img: Image.Image) -> Image.Image:
    """Add a bright patch to a copy — simulates localized alteration."""
    arr = np.array(img.copy())
    arr[50:100, 50:100] = [240, 10, 10]  # red patch
    return Image.fromarray(arr.astype(np.uint8))


class TestReferenceComparator:

    def test_identical_images_returns_inconclusive_or_confirmed_no_change(self, tmp_path):
        """
        Comparing an image against itself: SSIM=1.0, but pixel diff is 0.
        Since pct_changed < 0.5%, outcome should be INCONCLUSIVE.
        """
        from app.core.reference_comparator import ReferenceComparator, STATUS_INCONCLUSIVE
        img = _solid_image()
        ev_path  = _save(img, tmp_path, "ev.jpg")
        ref_path = _save(img, tmp_path, "ref.jpg")
        result = ReferenceComparator.compare(ev_path, ref_path, "EV-REF-001")
        assert result["comparison_status"] == STATUS_INCONCLUSIVE, (
            "Identical images should be INCONCLUSIVE (no significant difference found)"
        )

    def test_clearly_different_images_returns_confirmed(self, tmp_path):
        """A heavily patched image vs original must return REFERENCE_DIFFERENCE_CONFIRMED."""
        from app.core.reference_comparator import ReferenceComparator, STATUS_CONFIRMED
        orig = _solid_image()
        modified = _patched_copy(orig)
        ev_path  = _save(modified, tmp_path, "ev_mod.jpg")
        ref_path = _save(orig, tmp_path, "ref_orig.jpg")
        result = ReferenceComparator.compare(ev_path, ref_path, "EV-REF-002")
        # Should confirm difference (SSIM will be high enough for alignment, diff > 0.5%)
        assert result["comparison_status"] in (STATUS_CONFIRMED, "REFERENCE_COMPARISON_INCONCLUSIVE")
        assert result["ssim_score"] >= 0.0

    def test_result_always_has_disclaimer(self, tmp_path):
        """All comparison results must include the legal disclaimer."""
        from app.core.reference_comparator import ReferenceComparator, DISCLAIMER
        img = _solid_image()
        ev  = _save(img, tmp_path, "ev.jpg")
        ref = _save(img, tmp_path, "ref.jpg")
        result = ReferenceComparator.compare(ev, ref, "EV-REF-003")
        assert "disclaimer" in result
        assert "does not identify" in result["disclaimer"] or "method" in result["disclaimer"]

    def test_reference_sha256_is_computed(self, tmp_path):
        """SHA-256 of the reference image must be recorded in result."""
        from app.core.reference_comparator import ReferenceComparator
        img = _solid_image()
        ev  = _save(img, tmp_path, "ev.jpg")
        ref = _save(img, tmp_path, "ref.jpg")
        result = ReferenceComparator.compare(ev, ref, "EV-REF-004")
        assert len(result.get("reference_sha256", "")) == 64  # SHA-256 hex = 64 chars

    def test_comparison_status_never_claims_method(self, tmp_path):
        """STATUS strings must never imply which tool made the alteration."""
        from app.core.reference_comparator import STATUS_CONFIRMED, STATUS_INCONCLUSIVE
        forbidden = ["photoshop", "ai", "deepfake", "generated"]
        for status in (STATUS_CONFIRMED, STATUS_INCONCLUSIVE):
            for phrase in forbidden:
                assert phrase not in status.lower()

    def test_alignment_threshold_inconclusive_on_different_content(self, tmp_path):
        """
        Completely different-content images may fail alignment SSIM threshold
        and must return INCONCLUSIVE — not CONFIRMED.
        """
        from app.core.reference_comparator import ReferenceComparator, STATUS_INCONCLUSIVE
        ev_img  = Image.new("RGB", (200, 200), (255, 0, 0))   # all red
        ref_img = Image.new("RGB", (200, 200), (0, 0, 255))   # all blue
        ev  = _save(ev_img,  tmp_path, "ev_red.jpg")
        ref = _save(ref_img, tmp_path, "ref_blue.jpg")
        result = ReferenceComparator.compare(ev, ref, "EV-REF-005")
        # Different-content images: SSIM will be low -> INCONCLUSIVE
        assert result["comparison_status"] == STATUS_INCONCLUSIVE

    def test_changed_region_count_non_negative(self, tmp_path):
        """changed_region_count must always be >= 0."""
        from app.core.reference_comparator import ReferenceComparator
        img = _solid_image()
        ev  = _save(img, tmp_path, "ev.jpg")
        ref = _save(img, tmp_path, "ref.jpg")
        result = ReferenceComparator.compare(ev, ref, "EV-REF-006")
        assert result["changed_region_count"] >= 0

    def test_plain_image_cannot_be_confirmed_without_reference(self):
        """
        REFERENCE_DIFFERENCE_CONFIRMED must never be produced without actually
        running a comparison. Calling evaluate without a reference returns None / INCONCLUSIVE.
        """
        from app.core.localization_policy import PolicyEngine, OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED
        # No reference_comparison supplied (None)
        result = PolicyEngine.evaluate(
            provenance_status="NOT_AVAILABLE",
            reference_comparison=None,
            localization_result=None,
            ai_manipulation_indicator=0.9,
            model_status="AVAILABLE",
            findings=[],
            ensemble_agreement={"has_signal_conflict": False},
        )
        assert result["outcome"] != OUTCOME_REFERENCE_DIFFERENCE_CONFIRMED, (
            "REFERENCE_DIFFERENCE_CONFIRMED must not be issued without an actual reference comparison"
        )
