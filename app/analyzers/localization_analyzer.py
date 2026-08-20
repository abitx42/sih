"""
app/analyzers/localization_analyzer.py
=======================================
LocalizationAnalyzer — Multi-signal CPU heuristic image localization engine.

This module implements the full LocalizationAnalyzer contract using four
independent CPU-only signals:
  1. ELA spatial grid (16x16 cells, z-score per cell)
  2. Noise residual inconsistency map (Laplacian residuals)
  3. FFT block-boundary artifact detector
  4. Patch anomaly weighted heatmap

Model: TruthLens-LocalELA-v1 (CPU heuristic ensemble, no pretrained weights)

To upgrade to a pretrained localization model (TruFor, CAT-Net, ObjectFormer),
see LOCALIZATION_MODEL_SETUP.md. The LocalizationResult contract is identical
so a drop-in subclass requires only implementing analyze().

IMPORTANT LIMITATIONS (always reported in output):
  - CPU-only heuristic signals, not a trained segmentation model.
  - False positives common on heavily JPEG-compressed images.
  - Cannot determine the tool or method of any detected alteration.
  - Image-only analysis cannot prove AI generation, authenticity, or legal admissibility.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageChops, ImageEnhance
from scipy import ndimage

from app.config import FORENSIC_DIR

logger = logging.getLogger(__name__)

MODEL_NAME    = "TruthLens-LocalELA-v1"
MODEL_VERSION = "1.0.0"
MODEL_LIMITATIONS = (
    "CPU-only heuristic localization using ELA, Laplacian noise residuals, FFT block "
    "analysis, and patch-level anomaly scoring. No pretrained segmentation weights. "
    "Reliability scores reflect multi-signal agreement, not calibrated probabilities. "
    "False positives common on heavily JPEG-compressed or re-encoded images. "
    "Cannot determine the tool or method of any detected alteration."
)

LOCALIZATION_STATUS_AVAILABLE    = "AVAILABLE"
LOCALIZATION_STATUS_UNAVAILABLE  = "UNAVAILABLE"
LOCALIZATION_STATUS_INCONCLUSIVE = "INCONCLUSIVE"
LOCALIZATION_STATUS_ERROR        = "ERROR"


def _safe_float(v) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


class LocalizationAnalyzer:
    """
    Produces pixel-level localization of potential image manipulation.

    Returns a standardised dict (LocalizationResult contract):
      localization_status   : AVAILABLE | UNAVAILABLE | INCONCLUSIVE | ERROR
      global_integrity_score: float 0-1 (higher = more anomalous) | None
      manipulation_mask_path: str | None
      reliability_map_path  : str | None
      localized_regions     : list[RegionResult]
      model_name            : str
      model_version         : str
      model_limitations     : str
      error_detail          : str | None
    """

    def analyze(
        self,
        file_path: Path,
        evidence_id: str,
        img: Optional[Image.Image] = None,
    ) -> Dict[str, Any]:
        """
        Run multi-signal localization on an image file.

        Parameters
        ----------
        file_path   : Path to the stored evidence file
        evidence_id : Evidence ID for artifact naming
        img         : Pre-loaded PIL image (optional; loaded from file_path if None)
        """
        try:
            if img is None:
                img = Image.open(file_path).convert("RGB")
            else:
                img = img.convert("RGB")

            width, height = img.size
            if width < 64 or height < 64:
                return self._unavailable("Image too small for localization analysis (minimum 64x64 px).")

            # ── Signal 1: ELA spatial grid ────────────────────────────────────
            ela_grid, ela_img = self._ela_grid(img)

            # ── Signal 2: Noise residual map ──────────────────────────────────
            noise_map = self._noise_residual_map(img)

            # ── Signal 3: FFT block-boundary score per spatial cell ───────────
            fft_grid = self._fft_block_grid(img)

            # ── Signal 4: Patch anomaly heatmap ───────────────────────────────
            patch_heatmap = self._patch_heatmap(img, ela_img)

            # ── Combine signals into a unified anomaly map ────────────────────
            h, w = ela_grid.shape
            noise_r = _resize_array(noise_map, h, w)
            fft_r   = _resize_array(fft_grid,  h, w)
            patch_r = _resize_array(patch_heatmap, h, w)

            # Signal agreement reliability per pixel: how many of 4 signals agree
            threshold_ela   = np.percentile(ela_grid,   75)
            threshold_noise = np.percentile(noise_r,    75)
            threshold_fft   = np.percentile(fft_r,      75)
            threshold_patch = np.percentile(patch_r,    75)

            agree_count = (
                (ela_grid >= threshold_ela).astype(np.float32) +
                (noise_r  >= threshold_noise).astype(np.float32) +
                (fft_r    >= threshold_fft).astype(np.float32) +
                (patch_r  >= threshold_patch).astype(np.float32)
            )
            reliability_map_raw = agree_count / 4.0  # 0–1 per pixel

            # Combined anomaly = weighted mean of 4 signals
            combined = (
                ela_grid * 0.35
                + noise_r  * 0.30
                + patch_r  * 0.25
                + fft_r    * 0.10
            )
            combined = ndimage.gaussian_filter(combined, sigma=2.0)
            combined_norm = _normalize_01(combined)

            # Global integrity score = mean of top-10% anomalous pixels
            flat = combined_norm.flatten()
            top10_threshold = np.percentile(flat, 90)
            global_score = float(np.mean(flat[flat >= top10_threshold]))

            # ── Save artifacts ─────────────────────────────────────────────────
            mask_path = self._save_manipulation_mask(combined_norm, img, evidence_id)
            rel_path  = self._save_reliability_map(reliability_map_raw, img, evidence_id)

            # ── Extract bounding-box regions ───────────────────────────────────
            regions = self._extract_regions(
                combined_norm, reliability_map_raw, agree_count, width, height
            )

            if not regions and global_score < 0.25:
                return self._inconclusive(
                    global_score,
                    mask_path, rel_path,
                    "No localized anomaly clusters detected above threshold."
                )

            return {
                "localization_status": LOCALIZATION_STATUS_AVAILABLE,
                "global_integrity_score": round(global_score, 4),
                "manipulation_mask_path": str(mask_path) if mask_path else None,
                "reliability_map_path":   str(rel_path)  if rel_path  else None,
                "localized_regions": regions,
                "model_name": MODEL_NAME,
                "model_version": MODEL_VERSION,
                "model_limitations": MODEL_LIMITATIONS,
                "error_detail": None,
            }

        except Exception as exc:
            logger.warning(f"LocalizationAnalyzer error for {evidence_id}: {exc}", exc_info=True)
            return self._error(str(type(exc).__name__))

    # ── Signal extractors ─────────────────────────────────────────────────────

    def _ela_grid(self, img: Image.Image, grid: int = 16):
        """Returns normalised ELA energy grid (grid x grid) and ELA image."""
        try:
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=92)
            buf.seek(0)
            resaved = Image.open(buf).convert("RGB")
            diff = ImageChops.difference(img, resaved)
            diff_arr = np.array(diff, dtype=np.float32).mean(axis=2)  # grayscale
            h, w = diff_arr.shape
            gh, gw = max(1, h // grid), max(1, w // grid)
            grid_arr = np.zeros((grid, grid), dtype=np.float32)
            for i in range(grid):
                for j in range(grid):
                    cell = diff_arr[i*gh:(i+1)*gh, j*gw:(j+1)*gw]
                    grid_arr[i, j] = float(np.mean(cell))
            return _normalize_01(grid_arr), diff
        except Exception:
            return np.zeros((grid, grid), dtype=np.float32), None

    def _noise_residual_map(self, img: Image.Image, grid: int = 16) -> np.ndarray:
        """Returns grid-level Laplacian noise variance map."""
        try:
            gray = np.array(img.convert("L").resize((512, 512), Image.Resampling.BILINEAR),
                            dtype=np.float32)
            lap = ndimage.laplace(gray)
            h, w = lap.shape
            gh, gw = h // grid, w // grid
            grid_arr = np.zeros((grid, grid), dtype=np.float32)
            for i in range(grid):
                for j in range(grid):
                    cell = lap[i*gh:(i+1)*gh, j*gw:(j+1)*gw]
                    grid_arr[i, j] = float(np.var(cell))
            return _normalize_01(grid_arr)
        except Exception:
            return np.zeros((grid, grid), dtype=np.float32)

    def _fft_block_grid(self, img: Image.Image, grid: int = 16) -> np.ndarray:
        """
        Detects JPEG 8x8 block boundaries via FFT periodicity peaks.
        High values indicate block-boundary artefacts from JPEG re-encoding
        (common in splice or inpaint regions with different compression history).
        """
        try:
            gray = np.array(img.convert("L").resize((512, 512), Image.Resampling.BILINEAR),
                            dtype=np.float32)
            h, w = gray.shape
            gh, gw = h // grid, w // grid
            grid_arr = np.zeros((grid, grid), dtype=np.float32)
            for i in range(grid):
                for j in range(grid):
                    cell = gray[i*gh:(i+1)*gh, j*gw:(j+1)*gw]
                    if cell.size == 0:
                        continue
                    f = np.fft.fft2(cell - cell.mean())
                    mag = np.abs(f)
                    # Score = ratio of peak to mean (high ratio = periodic block pattern)
                    grid_arr[i, j] = float(np.max(mag) / (np.mean(mag) + 1e-6))
            return _normalize_01(grid_arr)
        except Exception:
            return np.zeros((grid, grid), dtype=np.float32)

    def _patch_heatmap(self, img: Image.Image, ela_img, grid: int = 16) -> np.ndarray:
        """Patch-level anomaly from ELA energy variance."""
        try:
            if ela_img is None:
                return np.zeros((grid, grid), dtype=np.float32)
            ela_arr = np.array(ela_img.convert("L").resize((512, 512), Image.Resampling.BILINEAR),
                               dtype=np.float32)
            h, w = ela_arr.shape
            gh, gw = h // grid, w // grid
            grid_arr = np.zeros((grid, grid), dtype=np.float32)
            for i in range(grid):
                for j in range(grid):
                    cell = ela_arr[i*gh:(i+1)*gh, j*gw:(j+1)*gw]
                    grid_arr[i, j] = float(np.mean(cell))
            return _normalize_01(grid_arr)
        except Exception:
            return np.zeros((grid, grid), dtype=np.float32)

    # ── Region extraction ─────────────────────────────────────────────────────

    def _extract_regions(
        self,
        combined: np.ndarray,      # grid H x W, values 0-1
        reliability: np.ndarray,   # grid H x W, values 0-1
        agree_count: np.ndarray,   # grid H x W, values 0-4
        img_w: int,
        img_h: int,
    ) -> List[Dict[str, Any]]:
        """Extracts top-3 anomalous bounding-box regions with neutral descriptions."""
        grid_h, grid_w = combined.shape
        cell_h = img_h / grid_h
        cell_w = img_w / grid_w

        # Threshold at 65th percentile of the anomaly map
        threshold = max(0.55, float(np.percentile(combined, 65)))
        hot_mask = combined >= threshold

        if not hot_mask.any():
            return []

        # Simple connected-component-like blob clustering
        labeled, num_features = ndimage.label(hot_mask)
        regions: List[Dict[str, Any]] = []

        for label_id in range(1, num_features + 1):
            if len(regions) >= 3:
                break
            component = labeled == label_id
            rows, cols = np.where(component)
            if len(rows) == 0:
                continue

            r_min, r_max = int(rows.min()), int(rows.max())
            c_min, c_max = int(cols.min()), int(cols.max())

            # Convert grid coords to normalized image coords
            ymin = round(r_min * cell_h / img_h, 3)
            xmin = round(c_min * cell_w / img_w, 3)
            ymax = round(min(1.0, (r_max + 1) * cell_h / img_h), 3)
            xmax = round(min(1.0, (c_max + 1) * cell_w / img_w), 3)

            px_x1 = int(c_min * cell_w)
            px_y1 = int(r_min * cell_h)
            px_x2 = int(min(img_w, (c_max + 1) * cell_w))
            px_y2 = int(min(img_h, (r_max + 1) * cell_h))

            region_combined = combined[component]
            region_reliability = reliability[component]
            region_agree = agree_count[component]

            avg_anomaly    = float(np.mean(region_combined))
            peak_anomaly   = float(np.max(region_combined))
            avg_reliability = float(np.mean(region_reliability))
            avg_agree       = float(np.mean(region_agree))

            # Affected area
            region_pixel_area = (px_x2 - px_x1) * (px_y2 - px_y1)
            total_area = img_w * img_h
            affected_pct = round(region_pixel_area / max(1, total_area) * 100.0, 2)

            # Severity based on anomaly score
            if peak_anomaly >= 0.80:
                severity = "HIGH"
            elif peak_anomaly >= 0.55:
                severity = "MEDIUM"
            else:
                severity = "LOW"

            # Neutral semantic location label
            cx = (xmin + xmax) / 2.0
            cy = (ymin + ymax) / 2.0
            location_label = _neutral_location_label(cx, cy)

            # Primary signal attribution (which signal drove this cluster)
            primary_signals = _primary_signals(avg_agree)

            # Neutral description — never claims tool or method
            neutral_desc = (
                f"Signal concentrated in {location_label.lower()}; "
                f"method of alteration undetermined. "
                f"Primary signal(s): {', '.join(primary_signals)}."
            )

            regions.append({
                "region_id": f"ROI-{len(regions) + 1}",
                "bounding_box": {
                    "ymin": ymin, "xmin": xmin,
                    "ymax": ymax, "xmax": xmax,
                    "pixel_coords": [px_x1, px_y1, px_x2, px_y2],
                },
                "affected_area_pct": affected_pct,
                "severity": severity,
                "reliability": round(min(0.85, avg_reliability + avg_agree / 20.0), 3),
                "neutral_description": neutral_desc,
                "primary_signals": primary_signals,
                "peak_anomaly_score": round(peak_anomaly, 3),
            })

        # Sort by reliability descending
        regions.sort(key=lambda r: r["reliability"], reverse=True)
        return regions

    # ── Artifact generation ───────────────────────────────────────────────────

    def _save_manipulation_mask(
        self, combined: np.ndarray, orig: Image.Image, evidence_id: str
    ) -> Optional[Path]:
        try:
            FORENSIC_DIR.mkdir(parents=True, exist_ok=True)
            h, w = combined.shape
            # Forensic colormap: dark-navy → cyan → yellow → crimson
            val = combined.astype(np.float32)
            rgb = np.zeros((h, w, 3), dtype=np.uint8)
            rgb[..., 0] = np.clip(np.where(val < 0.5, val * 2.0 * 50.0,
                                            50.0 + (val - 0.5) * 2.0 * 205.0), 0, 255).astype(np.uint8)
            rgb[..., 1] = np.clip(np.where(val < 0.5, val * 2.0 * 200.0,
                                            200.0 - (val - 0.5) * 2.0 * 180.0), 0, 255).astype(np.uint8)
            rgb[..., 2] = np.clip(np.where(val < 0.5, 120.0 + (1.0 - val * 2.0) * 100.0,
                                            (1.0 - (val - 0.5) * 2.0) * 80.0), 0, 255).astype(np.uint8)
            heat_img = Image.fromarray(rgb).resize(orig.size, Image.Resampling.BILINEAR)
            blended  = Image.blend(orig.convert("RGB"), heat_img, alpha=0.55)
            out_path = FORENSIC_DIR / f"localization_mask_{evidence_id}.png"
            blended.save(out_path, "PNG")
            return out_path
        except Exception as exc:
            logger.warning(f"Failed to save manipulation mask: {exc}")
            return None

    def _save_reliability_map(
        self, reliability: np.ndarray, orig: Image.Image, evidence_id: str
    ) -> Optional[Path]:
        try:
            FORENSIC_DIR.mkdir(parents=True, exist_ok=True)
            h, w = reliability.shape
            # Blue → Green reliability colormap
            val = (reliability * 255.0).clip(0, 255).astype(np.uint8)
            rgb = np.zeros((h, w, 3), dtype=np.uint8)
            rgb[..., 0] = 0
            rgb[..., 1] = val
            rgb[..., 2] = (255 - val)
            rel_img  = Image.fromarray(rgb).resize(orig.size, Image.Resampling.BILINEAR)
            blended  = Image.blend(orig.convert("RGB"), rel_img, alpha=0.45)
            out_path = FORENSIC_DIR / f"reliability_map_{evidence_id}.png"
            blended.save(out_path, "PNG")
            return out_path
        except Exception as exc:
            logger.warning(f"Failed to save reliability map: {exc}")
            return None

    # ── Result helpers ────────────────────────────────────────────────────────

    def _unavailable(self, reason: str) -> Dict[str, Any]:
        return {
            "localization_status": LOCALIZATION_STATUS_UNAVAILABLE,
            "global_integrity_score": None,
            "manipulation_mask_path": None,
            "reliability_map_path": None,
            "localized_regions": [],
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "model_limitations": MODEL_LIMITATIONS,
            "error_detail": reason,
        }

    def _inconclusive(self, score, mask, rel, reason) -> Dict[str, Any]:
        return {
            "localization_status": LOCALIZATION_STATUS_INCONCLUSIVE,
            "global_integrity_score": round(score, 4),
            "manipulation_mask_path": str(mask) if mask else None,
            "reliability_map_path":   str(rel)  if rel  else None,
            "localized_regions": [],
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "model_limitations": MODEL_LIMITATIONS,
            "error_detail": reason,
        }

    def _error(self, exc_type: str) -> Dict[str, Any]:
        return {
            "localization_status": LOCALIZATION_STATUS_ERROR,
            "global_integrity_score": None,
            "manipulation_mask_path": None,
            "reliability_map_path": None,
            "localized_regions": [],
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "model_limitations": MODEL_LIMITATIONS,
            "error_detail": f"Localization analysis raised {exc_type}. "
                            "Analysis unavailable for this exhibit.",
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_01(arr: np.ndarray) -> np.ndarray:
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-8:
        return np.zeros_like(arr, dtype=np.float32)
    return ((arr - mn) / (mx - mn)).astype(np.float32)


def _resize_array(arr: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """Resize a 2D array to target shape via PIL."""
    if arr.shape == (target_h, target_w):
        return arr
    try:
        img = Image.fromarray((arr * 255).clip(0, 255).astype(np.uint8))
        img = img.resize((target_w, target_h), Image.Resampling.BILINEAR)
        return np.array(img, dtype=np.float32) / 255.0
    except Exception:
        return np.zeros((target_h, target_w), dtype=np.float32)


def _neutral_location_label(cx: float, cy: float) -> str:
    """Returns a neutral spatial label — does not identify body parts or faces."""
    if cy < 0.33:
        row = "upper"
    elif cy > 0.67:
        row = "lower"
    else:
        row = "central"

    if cx < 0.33:
        col = "left"
    elif cx > 0.67:
        col = "right"
    else:
        col = "central"

    if row == "central" and col == "central":
        return "Central Region"
    if col == "central":
        return f"{row.capitalize()} Region"
    return f"{row.capitalize()}-{col} Region"


def _primary_signals(avg_agree: float) -> List[str]:
    """Maps average signal-agreement count to primary signal labels."""
    if avg_agree >= 3.5:
        return ["ELA_ANOMALY", "NOISE_INCONSISTENCY", "FFT_BLOCK_ARTIFACT", "PATCH_ANOMALY"]
    elif avg_agree >= 2.5:
        return ["ELA_ANOMALY", "NOISE_INCONSISTENCY", "PATCH_ANOMALY"]
    elif avg_agree >= 1.5:
        return ["ELA_ANOMALY", "NOISE_INCONSISTENCY"]
    elif avg_agree >= 0.5:
        return ["ELA_ANOMALY"]
    return ["HEURISTIC_SIGNAL"]
