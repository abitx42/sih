"""
Evidence Diff Engine
Compares two evidence files (by evidence_id or file path) and computes:
  - Pixel difference heatmap
  - Metadata field-by-field diff
  - Compression (ELA) delta
  - PRNU noise residual delta
  - Detected change regions (bounding boxes via PatchLocalizer on diff image)
"""
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)


def _pil_available() -> bool:
    try:
        from PIL import Image
        return True
    except ImportError:
        return False


class EvidenceDiffEngine:
    """
    Deterministic evidence comparison engine. All computation is numpy/PIL — no new ML models.
    Original stored files are never modified; all transforms are in-memory.
    """

    @staticmethod
    def compare(
        evidence_id_a: str,
        evidence_id_b: str,
        file_path_a: Path,
        file_path_b: Path,
        evidence_a: Dict[str, Any],
        evidence_b: Dict[str, Any],
        forensic_result_a: Optional[Dict[str, Any]] = None,
        forensic_result_b: Optional[Dict[str, Any]] = None,
        forensic_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Runs multi-signal comparison between two evidence files.
        Returns structured diff result dict.
        """
        result: Dict[str, Any] = {
            "diff_id": f"DIFF-{hashlib.sha256((evidence_id_a + evidence_id_b).encode()).hexdigest()[:10].upper()}",
            "evidence_id_a": evidence_id_a,
            "evidence_id_b": evidence_id_b,
            "filename_a": evidence_a.get("original_filename", "unknown"),
            "filename_b": evidence_b.get("original_filename", "unknown"),
            "modality_a": evidence_a.get("modality", "IMAGE"),
            "modality_b": evidence_b.get("modality", "IMAGE"),
            "compared_at": datetime.utcnow().isoformat() + "Z",
            "pixel_diff": None,
            "metadata_diff": [],
            "geometry_diff": {},
            "noise_diff": {},
            "detected_change_regions": [],
            "diff_heatmap_url": None,
            "summary": ""
        }

        # Only pixel-level diff for image modalities
        modality_a = evidence_a.get("modality", "IMAGE")
        modality_b = evidence_b.get("modality", "IMAGE")

        if modality_a != "IMAGE" or modality_b != "IMAGE":
            result["summary"] = "Pixel-level diff is only available for IMAGE modality evidence pairs. Metadata diff is shown below."
            result["metadata_diff"] = EvidenceDiffEngine._diff_metadata(evidence_a, evidence_b, forensic_result_a, forensic_result_b)
            return result

        try:
            from PIL import Image, ImageFilter
            img_a = Image.open(file_path_a).convert("RGB")
            img_b = Image.open(file_path_b).convert("RGB")
        except Exception as e:
            result["summary"] = f"Could not open one or both image files for comparison: {type(e).__name__}"
            result["metadata_diff"] = EvidenceDiffEngine._diff_metadata(evidence_a, evidence_b, forensic_result_a, forensic_result_b)
            return result

        # 1. Geometry diff
        w_a, h_a = img_a.size
        w_b, h_b = img_b.size
        result["geometry_diff"] = {
            "dimensions_a": f"{w_a}x{h_a}",
            "dimensions_b": f"{w_b}x{h_b}",
            "dimensions_match": (w_a == w_b and h_a == h_b),
            "scale_ratio_w": round(w_b / max(w_a, 1), 4),
            "scale_ratio_h": round(h_b / max(h_a, 1), 4),
            "resize_detected": abs(w_a - w_b) > 4 or abs(h_a - h_b) > 4
        }

        # Resize B to match A for pixel comparison if needed
        if (w_a, h_a) != (w_b, h_b):
            img_b_resized = img_b.resize((w_a, h_a), Image.LANCZOS)
        else:
            img_b_resized = img_b

        # 2. Pixel difference
        arr_a = np.array(img_a, dtype=np.int32)
        arr_b = np.array(img_b_resized, dtype=np.int32)
        diff_arr = np.abs(arr_a - arr_b)
        diff_mean = float(np.mean(diff_arr))
        diff_max = float(np.max(diff_arr))
        diff_pct_changed = float(np.mean(diff_arr.max(axis=2) > 10) * 100.0)

        result["pixel_diff"] = {
            "mean_absolute_difference": round(diff_mean, 3),
            "max_difference": round(diff_max, 1),
            "pct_pixels_changed": round(diff_pct_changed, 2),
            "significant_change": diff_pct_changed > 1.0
        }

        # 3. Noise residual delta (PRNU)
        try:
            from scipy import ndimage
            def _prnu_residual(arr):
                gray = np.mean(arr, axis=2)
                smooth = ndimage.gaussian_filter(gray.astype(float), sigma=3.0)
                return gray.astype(float) - smooth

            res_a = _prnu_residual(arr_a)
            res_b = _prnu_residual(arr_b)
            noise_delta = float(np.std(np.abs(res_a - res_b)))
            result["noise_diff"] = {
                "noise_residual_delta": round(noise_delta, 4),
                "noise_anomaly": noise_delta > 8.0
            }
        except Exception:
            result["noise_diff"] = {"noise_residual_delta": None, "noise_anomaly": False}

        # 4. Save diff heatmap
        diff_heatmap_url = None
        if forensic_dir:
            try:
                from PIL import Image as PILImage
                # Amplify diff for visibility
                diff_vis = np.clip(diff_arr * 4, 0, 255).astype(np.uint8)
                diff_img = PILImage.fromarray(diff_vis, mode="RGB")
                heatmap_filename = f"diff_{evidence_id_a}_{evidence_id_b}.png"
                heatmap_path = Path(forensic_dir) / heatmap_filename
                diff_img.save(str(heatmap_path))
                diff_heatmap_url = f"/api/diff/{evidence_id_a}/{evidence_id_b}/heatmap"
                result["diff_heatmap_url"] = diff_heatmap_url
                result["diff_heatmap_path"] = str(heatmap_path)
            except Exception as e:
                logger.warning(f"Failed to save diff heatmap: {e}")

        # 5. Detect change regions using bounding-box clustering on diff image
        try:
            result["detected_change_regions"] = EvidenceDiffEngine._detect_change_regions(diff_arr, w_a, h_a)
        except Exception as e:
            logger.warning(f"Change region detection failed: {e}")
            result["detected_change_regions"] = []

        # 6. Metadata diff
        result["metadata_diff"] = EvidenceDiffEngine._diff_metadata(evidence_a, evidence_b, forensic_result_a, forensic_result_b)

        # 7. Summary
        changed_px = result["pixel_diff"]["pct_pixels_changed"]
        n_regions = len(result["detected_change_regions"])
        if changed_px < 0.5:
            summary = f"Files appear visually nearly identical ({changed_px:.2f}% pixels differ). Minor recompression or metadata-only differences possible."
        elif n_regions > 0:
            labels = [r.get("label", "Region") for r in result["detected_change_regions"][:3]]
            summary = f"{changed_px:.1f}% of pixels changed. {n_regions} distinct change region(s) detected: {', '.join(labels)}."
        else:
            summary = f"{changed_px:.1f}% of pixels changed across the frame (no distinct localized region clustered)."

        result["summary"] = summary
        return result

    @staticmethod
    def _detect_change_regions(diff_arr: np.ndarray, width: int, height: int) -> List[Dict[str, Any]]:
        """
        Clusters high-difference pixels into bounding-box regions.
        Uses a simple grid-based approach — no ML required.
        """
        regions = []
        # Use a 4x4 grid of quadrants
        grid_rows, grid_cols = 4, 4
        cell_h = max(1, height // grid_rows)
        cell_w = max(1, width // grid_cols)

        diff_mag = diff_arr.max(axis=2)  # H x W

        quadrant_scores = []
        for r in range(grid_rows):
            for c in range(grid_cols):
                y0 = r * cell_h
                y1 = height if r == grid_rows - 1 else min(height, (r + 1) * cell_h)
                x0 = c * cell_w
                x1 = width if c == grid_cols - 1 else min(width, (c + 1) * cell_w)
                cell = diff_mag[y0:y1, x0:x1]
                score = float(np.mean(cell > 15))  # fraction of changed pixels
                if score > 0.15:  # >15% of this quadrant changed
                    quadrant_scores.append({
                        "bounding_box": [x0, y0, x1, y1],
                        "score": round(score, 3),
                        "change_pct": round(score * 100, 1)
                    })

        # Label top regions by approximate position
        def _label_region(box):
            cx = (box[0] + box[2]) / 2 / width
            cy = (box[1] + box[3]) / 2 / height
            vert = "Upper" if cy < 0.4 else ("Lower" if cy > 0.65 else "Middle")
            horiz = "Left" if cx < 0.35 else ("Right" if cx > 0.65 else "Center")
            return f"{vert} {horiz} Region"

        top_regions = sorted(quadrant_scores, key=lambda x: x["score"], reverse=True)[:5]
        for region in top_regions:
            region["label"] = _label_region(region["bounding_box"])
            regions.append(region)

        return regions

    @staticmethod
    def _diff_metadata(
        evidence_a: Dict[str, Any],
        evidence_b: Dict[str, Any],
        forensic_result_a: Optional[Dict[str, Any]],
        forensic_result_b: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Field-by-field structural metadata comparison.
        """
        diffs = []

        def _add(field, val_a, val_b):
            if str(val_a) != str(val_b):
                diffs.append({"field": field, "value_a": str(val_a) if val_a is not None else "—", "value_b": str(val_b) if val_b is not None else "—", "changed": True})
            else:
                diffs.append({"field": field, "value_a": str(val_a) if val_a is not None else "—", "value_b": str(val_b) if val_b is not None else "—", "changed": False})

        _add("File Size (bytes)", evidence_a.get("file_size_bytes"), evidence_b.get("file_size_bytes"))
        _add("SHA-256", evidence_a.get("sha256_hash", "")[:20] + "...", evidence_b.get("sha256_hash", "")[:20] + "...")
        _add("Modality", evidence_a.get("modality"), evidence_b.get("modality"))

        if forensic_result_a and forensic_result_b:
            _add("Risk Category", forensic_result_a.get("risk_category"), forensic_result_b.get("risk_category"))
            _add("Forensic Risk Score", forensic_result_a.get("forensic_risk_score"), forensic_result_b.get("forensic_risk_score"))
            _add("Forensic Taxonomy", forensic_result_a.get("forensic_taxonomy"), forensic_result_b.get("forensic_taxonomy"))
            _add("Provenance Status", forensic_result_a.get("provenance_status"), forensic_result_b.get("provenance_status"))
            _add("AI Manipulation Indicator", forensic_result_a.get("ai_manipulation_indicator"), forensic_result_b.get("ai_manipulation_indicator"))

            # EXIF fields from raw metrics
            def _exif(fr):
                try:
                    rm = json.loads(fr.get("raw_metrics_json") or "{}")
                    return rm.get("exif", {})
                except Exception:
                    return {}

            exif_a = _exif(forensic_result_a)
            exif_b = _exif(forensic_result_b)
            for key in ["Make", "Model", "Software", "DateTimeOriginal", "GPSInfo"]:
                va = exif_a.get(key)
                vb = exif_b.get(key)
                if va is not None or vb is not None:
                    _add(f"EXIF: {key}", va, vb)

        return [d for d in diffs if d["changed"]] + [d for d in diffs if not d["changed"]]
