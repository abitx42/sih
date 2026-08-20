"""
app/core/reference_comparator.py
=================================
Trusted-Reference Image Comparison Engine.

Compares an evidence image against an investigator-supplied reference original.
Produces a difference map and change-region annotations.

IMPORTANT:
  - "REFERENCE_DIFFERENCE_CONFIRMED" means structural pixel differences were
    detected between the two images. It does NOT identify the tool or method
    of any alteration.
  - "REFERENCE_COMPARISON_INCONCLUSIVE" means alignment failed or differences
    were below significance threshold.
  - This comparison proves image differences against the supplied reference.
    It cannot determine which image is "original".
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from app.config import FORENSIC_DIR, settings

logger = logging.getLogger(__name__)

STATUS_CONFIRMED    = "REFERENCE_DIFFERENCE_CONFIRMED"
STATUS_INCONCLUSIVE = "REFERENCE_COMPARISON_INCONCLUSIVE"

DISCLAIMER = (
    "This comparison proves structural pixel differences between the evidence image and the "
    "supplied reference. It does not identify the tool or method of any alteration, nor does "
    "it determine which image is the unmodified original."
)


class ReferenceComparator:
    """
    Aligns two images and computes a pixel-level difference map.

    SSIM (Structural Similarity Index) is used to assess alignment quality.
    A comparison succeeds (STATUS_CONFIRMED) only when:
      - Both images are valid images,
      - Alignment SSIM >= settings.REFERENCE_COMPARISON_ALIGNMENT_THRESHOLD, AND
      - At least some pixels differ significantly.

    All operations are CPU-only using numpy/PIL. scipy.ndimage is used for
    structural similarity approximation without importing scikit-image.
    """

    @staticmethod
    def compute_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def compare(
        evidence_path: Path,
        reference_path: Path,
        evidence_id: str,
        submitted_by: str = "Investigator",
    ) -> Dict[str, Any]:
        """
        Compare evidence image against a reference image.

        Returns a dict with:
          comparison_status : STATUS_CONFIRMED | STATUS_INCONCLUSIVE
          ssim_score        : float (0–1)
          alignment_succeeded : bool
          reference_sha256  : str
          difference_map_path : str | None
          changed_regions   : list
          changed_region_count : int
          disclaimer        : str
        """
        try:
            ref_sha256 = ReferenceComparator.compute_sha256(reference_path)

            ev_img  = Image.open(evidence_path).convert("RGB")
            ref_img = Image.open(reference_path).convert("RGB")

            # Align: resize both to a common resolution (smallest of the two)
            ev_w,  ev_h  = ev_img.size
            ref_w, ref_h = ref_img.size
            target_w = min(ev_w, ref_w, 1024)
            target_h = min(ev_h, ref_h, 1024)

            ev_r  = ev_img.resize( (target_w, target_h), Image.Resampling.LANCZOS)
            ref_r = ref_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            ev_arr  = np.array(ev_r,  dtype=np.float32) / 255.0
            ref_arr = np.array(ref_r, dtype=np.float32) / 255.0

            # Structural similarity approximation (fast, no scikit-image)
            ssim_score = _fast_ssim(ev_arr, ref_arr)
            alignment_succeeded = ssim_score >= settings.REFERENCE_COMPARISON_ALIGNMENT_THRESHOLD

            # Pixel-level difference
            diff_arr = np.abs(ev_arr - ref_arr)                    # H x W x 3
            diff_gray = diff_arr.mean(axis=2)                      # H x W
            pct_changed = float((diff_gray > 0.05).mean() * 100.0) # > 5/255 threshold

            diff_map_path = _save_difference_map(diff_gray, ev_r, evidence_id)

            changed_regions = _detect_changed_regions(diff_gray)

            if not alignment_succeeded or pct_changed < 0.5:
                reason = (
                    f"Alignment SSIM={ssim_score:.3f} below threshold "
                    f"{settings.REFERENCE_COMPARISON_ALIGNMENT_THRESHOLD}"
                    if not alignment_succeeded
                    else f"Changed pixel fraction {pct_changed:.2f}% below significance threshold (0.5%)"
                )
                return {
                    "comparison_status": STATUS_INCONCLUSIVE,
                    "ssim_score": round(ssim_score, 4),
                    "alignment_succeeded": alignment_succeeded,
                    "reference_sha256": ref_sha256,
                    "difference_map_path": str(diff_map_path) if diff_map_path else None,
                    "changed_regions": [],
                    "changed_region_count": 0,
                    "pct_pixels_changed": round(pct_changed, 2),
                    "reason": reason,
                    "disclaimer": DISCLAIMER,
                }

            return {
                "comparison_status": STATUS_CONFIRMED,
                "ssim_score": round(ssim_score, 4),
                "alignment_succeeded": True,
                "reference_sha256": ref_sha256,
                "difference_map_path": str(diff_map_path) if diff_map_path else None,
                "changed_regions": changed_regions,
                "changed_region_count": len(changed_regions),
                "pct_pixels_changed": round(pct_changed, 2),
                "disclaimer": DISCLAIMER,
            }

        except Exception as exc:
            logger.warning(f"ReferenceComparator error for {evidence_id}: {exc}", exc_info=True)
            return {
                "comparison_status": STATUS_INCONCLUSIVE,
                "ssim_score": 0.0,
                "alignment_succeeded": False,
                "reference_sha256": "",
                "difference_map_path": None,
                "changed_regions": [],
                "changed_region_count": 0,
                "pct_pixels_changed": 0.0,
                "reason": f"Comparison failed: {type(exc).__name__}",
                "disclaimer": DISCLAIMER,
            }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fast_ssim(a: np.ndarray, b: np.ndarray) -> float:
    """
    Fast structural similarity approximation without scikit-image.
    Mean-luminance and contrast comparison over global image statistics.
    Range: 0 (completely different) to 1 (identical).
    """
    try:
        mu_a, mu_b = a.mean(), b.mean()
        sigma_a = float(np.std(a))
        sigma_b = float(np.std(b))
        sigma_ab = float(np.mean((a - mu_a) * (b - mu_b)))
        C1 = (0.01 ** 2)
        C2 = (0.03 ** 2)
        numerator   = (2 * mu_a * mu_b + C1) * (2 * sigma_ab + C2)
        denominator = (mu_a**2 + mu_b**2 + C1) * (sigma_a**2 + sigma_b**2 + C2)
        return float(np.clip(numerator / (denominator + 1e-8), 0.0, 1.0))
    except Exception:
        return 0.0


def _detect_changed_regions(diff_gray: np.ndarray, grid: int = 8) -> List[Dict[str, Any]]:
    """Partitions image into grid cells and returns cells with > 15% changed pixels."""
    h, w = diff_gray.shape
    gh, gw = max(1, h // grid), max(1, w // grid)
    regions = []
    for i in range(grid):
        for j in range(grid):
            cell = diff_gray[i*gh:(i+1)*gh, j*gw:(j+1)*gw]
            changed_pct = float((cell > 0.05).mean() * 100.0)
            if changed_pct >= 15.0:
                regions.append({
                    "grid_row": i,
                    "grid_col": j,
                    "changed_pct": round(changed_pct, 1),
                    "mean_diff": round(float(cell[cell > 0.05].mean()) if (cell > 0.05).any() else 0.0, 4),
                    "neutral_description": f"Region ({i+1},{j+1}) shows {changed_pct:.0f}% pixel difference from reference.",
                })
    return regions


def _save_difference_map(diff_gray: np.ndarray, orig: Image.Image, evidence_id: str) -> Optional[Path]:
    """Saves a heatmap of pixel differences blended onto the evidence image."""
    try:
        FORENSIC_DIR.mkdir(parents=True, exist_ok=True)
        h, w = diff_gray.shape
        # Red = changed, dark = unchanged
        norm = (diff_gray * 5.0).clip(0, 1)
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        rgb[..., 0] = (norm * 255).astype(np.uint8)
        rgb[..., 1] = ((1 - norm) * 60).astype(np.uint8)
        rgb[..., 2] = ((1 - norm) * 60).astype(np.uint8)
        heat_img = Image.fromarray(rgb).resize(orig.size, Image.Resampling.BILINEAR)
        blended = Image.blend(orig.convert("RGB"), heat_img, alpha=0.50)
        out_path = FORENSIC_DIR / f"reference_diff_{evidence_id}.png"
        blended.save(out_path, "PNG")
        return out_path
    except Exception as exc:
        logger.warning(f"Failed to save difference map: {exc}")
        return None
