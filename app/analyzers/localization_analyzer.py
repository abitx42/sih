"""
app/analyzers/localization_analyzer.py
=======================================
LocalizationAnalyzer — Multi-signal CPU heuristic image anomaly concentration engine.

This module implements the LocalizationAnalyzer contract using four complementary
CPU heuristic spatial signals:
  1. ELA spatial grid (16x16 cells, z-score per cell)
  2. Noise residual variance map (Laplacian residuals)
  3. FFT block-boundary artifact detector
  4. Patch anomaly weighted heatmap

Model: TruthLens-LocalELA-v1 (CPU heuristic ensemble, uncalibrated, no pretrained weights)

SCIENTIFIC & CALIBRATION RULES:
  - This is a CPU heuristic system, NOT a trained or calibrated segmentation model.
  - The signals share underlying image compression and sensor-noise information;
    they are NOT independent detectors.
  - The output heatmap represents statistical anomaly concentration only, NOT pixel-level
    proof of manipulation.
  - No unvalidated confidence percentages are output.
  - Calibration status is visibly reported as UNVALIDATED.
  - Alteration method, editing tool, and whether AI was used cannot be determined from this result.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageChops
from scipy import ndimage

from app.config import FORENSIC_DIR

logger = logging.getLogger(__name__)

MODEL_NAME    = "TruthLens-LocalELA-v1"
MODEL_VERSION = "1.0.0"
CALIBRATION_STATUS = "UNVALIDATED"
MODEL_LIMITATIONS = (
    "CPU heuristic system analyzing statistical anomaly concentration across ELA, "
    "Laplacian noise residuals, FFT block periodicity, and patch variance. "
    "Some signals share underlying compression/noise information and are not independent deep learning models. "
    "Output reflects spatial anomaly concentration only, not pixel-level proof of manipulation. "
    "Alteration method, editing tool, and whether AI was used cannot be determined from this result. "
    "Calibration status is UNVALIDATED; values reflect rule-based anomaly scoring rather than verified probabilities."
)

LOCALIZATION_STATUS_AVAILABLE    = "AVAILABLE"
LOCALIZATION_STATUS_UNAVAILABLE  = "UNAVAILABLE"
LOCALIZATION_STATUS_INCONCLUSIVE = "INCONCLUSIVE"
LOCALIZATION_STATUS_ERROR        = "ERROR"


class LocalizationAnalyzer:
    """
    Produces spatial localization of statistical anomaly concentrations in an image.

    Returns a standardized dictionary conforming to the LocalizationResult contract:
      localization_status           : AVAILABLE | UNAVAILABLE | INCONCLUSIVE | ERROR
      global_anomaly_score          : float 0-1 (higher = higher anomaly concentration) | None
      localized_anomaly_heatmap_path: str | None
      reliability_map_path          : str | None
      calibration_status            : "UNVALIDATED"
      localized_regions             : list[RegionResult]
      model_name                    : str
      model_version                 : str
      model_limitations             : str
      error_detail                  : str | None
    """

    def analyze(
        self,
        file_path: Path,
        evidence_id: str,
        img: Optional[Image.Image] = None,
    ) -> Dict[str, Any]:
        """
        Run multi-signal heuristic anomaly localization on an image file.
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

            # ── Combine signals into unified anomaly concentration map ────────
            h, w = ela_grid.shape
            noise_r = _resize_array(noise_map, h, w)
            fft_r   = _resize_array(fft_grid,  h, w)
            patch_r = _resize_array(patch_heatmap, h, w)

            # Signal agreement per cell: count how many heuristic calculations flag an anomaly
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
            agreement_map_raw = agree_count / 4.0  # 0 to 1 proportion

            # Combined anomaly = weighted combination of shared heuristic signals
            combined = (
                ela_grid * 0.35
                + noise_r  * 0.30
                + patch_r  * 0.25
                + fft_r    * 0.10
            )
            combined = ndimage.gaussian_filter(combined, sigma=2.0)
            combined_norm = _normalize_01(combined)

            # Global anomaly score = mean of top-10% anomalous pixels
            flat = combined_norm.flatten()
            top10_threshold = np.percentile(flat, 90)
            global_score = float(np.mean(flat[flat >= top10_threshold]))

            # ── Save visual artifacts ──────────────────────────────────────────
            heatmap_path = self._save_anomaly_heatmap(combined_norm, img, evidence_id)
            rel_path     = self._save_agreement_map(agreement_map_raw, img, evidence_id)

            # ── Extract bounded suspicious regions ────────────────────────────
            regions = self._extract_regions(
                combined_norm, agreement_map_raw, agree_count, width, height
            )

            if not regions and global_score < 0.25:
                return self._inconclusive(
                    global_score,
                    heatmap_path, rel_path,
                    "No localized anomaly concentrations detected above threshold."
                )

            return {
                "localization_status": LOCALIZATION_STATUS_AVAILABLE,
                "global_anomaly_score": round(global_score, 4),
                "localized_anomaly_heatmap_path": str(heatmap_path) if heatmap_path else None,
                # Retain backwards-compatible alias for existing endpoints
                "manipulation_mask_path": str(heatmap_path) if heatmap_path else None,
                "reliability_map_path": str(rel_path) if rel_path else None,
                "calibration_status": CALIBRATION_STATUS,
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
        try:
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=92)
            buf.seek(0)
            resaved = Image.open(buf).convert("RGB")
            diff = ImageChops.difference(img, resaved)
            diff_arr = np.array(diff, dtype=np.float32).mean(axis=2)
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
                    grid_arr[i, j] = float(np.max(mag) / (np.mean(mag) + 1e-6))
            return _normalize_01(grid_arr)
        except Exception:
            return np.zeros((grid, grid), dtype=np.float32)

    def _patch_heatmap(self, img: Image.Image, ela_img, grid: int = 16) -> np.ndarray:
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
        combined: np.ndarray,
        agreement: np.ndarray,
        agree_count: np.ndarray,
        img_w: int,
        img_h: int,
    ) -> List[Dict[str, Any]]:
        grid_h, grid_w = combined.shape
        cell_h = img_h / grid_h
        cell_w = img_w / grid_w

        threshold = max(0.55, float(np.percentile(combined, 65)))
        hot_mask = combined >= threshold

        if not hot_mask.any():
            return []

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

            ymin = round(r_min * cell_h / img_h, 3)
            xmin = round(c_min * cell_w / img_w, 3)
            ymax = round(min(1.0, (r_max + 1) * cell_h / img_h), 3)
            xmax = round(min(1.0, (c_max + 1) * cell_w / img_w), 3)

            px_x1 = int(c_min * cell_w)
            px_y1 = int(r_min * cell_h)
            px_x2 = int(min(img_w, (c_max + 1) * cell_w))
            px_y2 = int(min(img_h, (r_max + 1) * cell_h))

            region_combined = combined[component]
            region_agree = agree_count[component]

            peak_anomaly = float(np.max(region_combined))
            avg_agree    = float(np.mean(region_agree))

            region_pixel_area = (px_x2 - px_x1) * (px_y2 - px_y1)
            total_area = img_w * img_h
            affected_pct = round(region_pixel_area / max(1, total_area) * 100.0, 2)

            # Evidence strength: rule-based classification (not a calibrated probability)
            if peak_anomaly >= 0.80 and avg_agree >= 2.5:
                evidence_strength = "HIGH"
                severity = "HIGH"
            elif peak_anomaly >= 0.55 and avg_agree >= 1.5:
                evidence_strength = "MODERATE"
                severity = "MEDIUM"
            else:
                evidence_strength = "LOW"
                severity = "LOW"

            cx = (xmin + xmax) / 2.0
            cy = (ymin + ymax) / 2.0
            location_label = _neutral_location_label(cx, cy)
            primary_signals = _primary_signals(avg_agree)

            # Neutral description: strictly avoids claiming tool or AI usage
            neutral_desc = (
                f"Statistical anomaly concentration detected in {location_label.lower()}. "
                f"Alteration method, editing tool, and whether AI was used cannot be determined from this result. "
                f"Contributing signals: {', '.join(primary_signals)}."
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
                "evidence_strength": evidence_strength,
                "signal_agreement": f"{int(round(min(4, max(1, avg_agree))))} of 4 heuristic signals",
                "calibration_status": CALIBRATION_STATUS,
                "neutral_description": neutral_desc,
                "primary_signals": primary_signals,
                "peak_anomaly_score": round(peak_anomaly, 3),
            })

        return regions

    # ── Artifact generation ───────────────────────────────────────────────────

    def _save_anomaly_heatmap(
        self, combined: np.ndarray, orig: Image.Image, evidence_id: str
    ) -> Optional[Path]:
        try:
            FORENSIC_DIR.mkdir(parents=True, exist_ok=True)
            h, w = combined.shape
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
            out_path = FORENSIC_DIR / f"localized_anomaly_heatmap_{evidence_id}.png"
            blended.save(out_path, "PNG")
            return out_path
        except Exception as exc:
            logger.warning(f"Failed to save anomaly heatmap: {exc}")
            return None

    def _save_agreement_map(
        self, agreement: np.ndarray, orig: Image.Image, evidence_id: str
    ) -> Optional[Path]:
        try:
            FORENSIC_DIR.mkdir(parents=True, exist_ok=True)
            h, w = agreement.shape
            val = (agreement * 255.0).clip(0, 255).astype(np.uint8)
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
            logger.warning(f"Failed to save agreement map: {exc}")
            return None

    # ── Result helpers ────────────────────────────────────────────────────────

    def _unavailable(self, reason: str) -> Dict[str, Any]:
        return {
            "localization_status": LOCALIZATION_STATUS_UNAVAILABLE,
            "global_anomaly_score": None,
            "localized_anomaly_heatmap_path": None,
            "manipulation_mask_path": None,
            "reliability_map_path": None,
            "calibration_status": CALIBRATION_STATUS,
            "localized_regions": [],
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "model_limitations": MODEL_LIMITATIONS,
            "error_detail": reason,
        }

    def _inconclusive(self, score, heatmap, rel, reason) -> Dict[str, Any]:
        return {
            "localization_status": LOCALIZATION_STATUS_INCONCLUSIVE,
            "global_anomaly_score": round(score, 4),
            "localized_anomaly_heatmap_path": str(heatmap) if heatmap else None,
            "manipulation_mask_path": str(heatmap) if heatmap else None,
            "reliability_map_path":   str(rel)  if rel  else None,
            "calibration_status": CALIBRATION_STATUS,
            "localized_regions": [],
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "model_limitations": MODEL_LIMITATIONS,
            "error_detail": reason,
        }

    def _error(self, exc_type: str) -> Dict[str, Any]:
        return {
            "localization_status": LOCALIZATION_STATUS_ERROR,
            "global_anomaly_score": None,
            "localized_anomaly_heatmap_path": None,
            "manipulation_mask_path": None,
            "reliability_map_path": None,
            "calibration_status": CALIBRATION_STATUS,
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
    if arr.shape == (target_h, target_w):
        return arr
    try:
        img = Image.fromarray((arr * 255).clip(0, 255).astype(np.uint8))
        img = img.resize((target_w, target_h), Image.Resampling.BILINEAR)
        return np.array(img, dtype=np.float32) / 255.0
    except Exception:
        return np.zeros((target_h, target_w), dtype=np.float32)


def _neutral_location_label(cx: float, cy: float) -> str:
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
    if avg_agree >= 3.5:
        return ["ELA Anomaly", "Noise Inconsistency", "FFT Block Boundary", "Patch Anomaly"]
    elif avg_agree >= 2.5:
        return ["ELA Anomaly", "Noise Inconsistency", "Patch Anomaly"]
    elif avg_agree >= 1.5:
        return ["ELA Anomaly", "Noise Inconsistency"]
    elif avg_agree >= 0.5:
        return ["ELA Anomaly"]
    return ["Heuristic Anomaly Signal"]
