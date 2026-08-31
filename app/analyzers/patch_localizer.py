import os
import math
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image, ImageChops, ImageDraw
import numpy as np
from scipy import ndimage

from app.config import FORENSIC_DIR

class PatchLocalizer:
    """
    Spatial Patch Forensics & Localized Manipulation Localizer.
    
    Deconstructs images into spatial patches to detect localized anomalies:
    1. Local Noise Residual Inconsistency (Laplacian sensor-noise variance)
    2. Localized Error Level Discrepancy (Patch ELA vs Global Baseline)
    3. Boundary Resampling & Spatial Gradient Discontinuities
    
    Produces:
    - 2D Spatial Anomaly Heatmap (saved to storage/forensic/)
    - Detected Bounding Boxes for anomalous ROIs (e.g. Eyewear/Face/Inpainting)
    - Patch Anomaly Distribution Metrics
    """

    def __init__(self, target_patch_size: int = 64):
        self.target_patch_size = target_patch_size

    def analyze_patches(
        self,
        img: Image.Image,
        ela_img: Optional[Image.Image],
        evidence_id: str
    ) -> Dict[str, Any]:
        """
        Decomposes the image into sliding window patches, computes localized
        forensic anomalies, generates a spatial heatmap, and extracts anomalous bounding boxes.
        """
        width, height = img.size
        # Fast processing scale guard for high-resolution images (> 1024px)
        if max(width, height) > 1024:
            scale = 1024.0 / max(width, height)
            target_w = max(64, int(width * scale))
            target_h = max(64, int(height * scale))
            img_proc = img.resize((target_w, target_h), Image.Resampling.BILINEAR)
            gray = np.array(img_proc.convert("L"), dtype=np.float32)
            if ela_img is not None:
                ela_proc = ela_img.resize((target_w, target_h), Image.Resampling.BILINEAR)
                ela_gray = np.array(ela_proc.convert("L"), dtype=np.float32)
            else:
                ela_gray = np.zeros_like(gray)
            width, height = target_w, target_h
        else:
            gray = np.array(img.convert("L"), dtype=np.float32)
            if ela_img is not None:
                ela_gray = np.array(ela_img.convert("L"), dtype=np.float32)
            else:
                ela_gray = np.zeros_like(gray)

        # 1. Compute High-Pass Noise Residual (Sensor Noise Pattern)
        # Low-pass gaussian subtracted from original yields high-frequency residual
        low_pass = ndimage.gaussian_filter(gray, sigma=1.5)
        noise_residual = np.abs(gray - low_pass)

        # 2. Compute Spatial Gradient Magnitude (Boundary / Resampling traces)
        sobel_h = ndimage.sobel(gray, axis=0)
        sobel_v = ndimage.sobel(gray, axis=1)
        gradient_mag = np.hypot(sobel_h, sobel_v)

        # Adaptive patch size based on image dimensions
        min_dim = min(width, height)
        patch_size = max(8, min(self.target_patch_size, min_dim))
        stride = max(1, min(16, patch_size // 2))

        # Sliding window analysis
        patches: List[Dict[str, Any]] = []
        noise_variances = []
        ela_energies = []
        grad_disparities = []

        y_steps = range(0, max(1, height - patch_size + 1), stride)
        x_steps = range(0, max(1, width - patch_size + 1), stride)

        for y in y_steps:
            for x in x_steps:
                y2 = min(height, y + patch_size)
                x2 = min(width, x + patch_size)

                p_noise = noise_residual[y:y2, x:x2]
                p_ela = ela_gray[y:y2, x:x2]
                p_grad = gradient_mag[y:y2, x:x2]

                n_var = float(np.var(p_noise))
                e_val = float(np.mean(p_ela))
                g_val = float(np.std(p_grad))

                noise_variances.append(n_var)
                ela_energies.append(e_val)
                grad_disparities.append(g_val)

                patches.append({
                    "box": [y, x, y2, x2],
                    "noise_var": n_var,
                    "ela_energy": e_val,
                    "grad_disp": g_val
                })

        if not patches:
            return {
                "max_patch_anomaly": 0.0,
                "localized_regions": [],
                "heatmap_path": None,
                "patch_count": 0
            }

        # Calculate robust statistics (Median & MAD) for baseline reference
        n_arr = np.array(noise_variances, dtype=np.float32)
        e_arr = np.array(ela_energies, dtype=np.float32)
        g_arr = np.array(grad_disparities, dtype=np.float32)

        med_noise = float(np.median(n_arr))
        mad_noise = max(2.0, float(np.median(np.abs(n_arr - med_noise))))

        med_ela = float(np.median(e_arr))
        mad_ela = max(1.5, float(np.median(np.abs(e_arr - med_ela))))

        med_grad = float(np.median(g_arr))
        mad_grad = max(1.5, float(np.median(np.abs(g_arr - med_grad))))

        # Compute normalized anomaly scores per patch and construct 2D heatmap accumulator
        heatmap_accum = np.zeros((height, width), dtype=np.float32)
        heatmap_weight = np.zeros((height, width), dtype=np.float32)

        for p in patches:
            y, x, y2, x2 = p["box"]

            z_noise = abs(p["noise_var"] - med_noise) / mad_noise
            z_ela = abs(p["ela_energy"] - med_ela) / mad_ela
            z_grad = abs(p["grad_disp"] - med_grad) / mad_grad

            # Sigmoid/capped normalization to 0.0 - 1.0
            score_noise = min(1.0, z_noise / 4.0)
            score_ela = min(1.0, z_ela / 4.0)
            score_grad = min(1.0, z_grad / 4.0)

            # Combined patch anomaly score
            patch_score = (score_noise * 0.40) + (score_ela * 0.35) + (score_grad * 0.25)
            p["anomaly_score"] = float(patch_score)

            heatmap_accum[y:y2, x:x2] += patch_score
            heatmap_weight[y:y2, x:x2] += 1.0

        # Normalize heatmap
        nonzero_mask = heatmap_weight > 0
        heatmap = np.zeros((height, width), dtype=np.float32)
        heatmap[nonzero_mask] = heatmap_accum[nonzero_mask] / heatmap_weight[nonzero_mask]

        # Smooth heatmap slightly
        heatmap = ndimage.gaussian_filter(heatmap, sigma=max(2.0, patch_size / 8.0))
        max_anomaly = float(np.max(heatmap)) if heatmap.size > 0 else 0.0

        orig_w, orig_h = img.size
        # Extract localized high-anomaly bounding boxes
        localized_regions = self._extract_bounding_boxes(
            heatmap=heatmap,
            patches=patches,
            width=width,
            height=height,
            orig_w=orig_w,
            orig_h=orig_h,
            max_anomaly=max_anomaly
        )

        # Generate and save colored visualization heatmap image
        heatmap_path = self._save_heatmap_image(heatmap, img, evidence_id)

        return {
            "max_patch_anomaly": round(max_anomaly * 100.0, 1),
            "mean_patch_anomaly": round(float(np.mean(heatmap)) * 100.0, 1),
            "localized_regions": localized_regions,
            "heatmap_path": str(heatmap_path) if heatmap_path else None,
            "patch_count": len(patches),
            "baseline_noise_variance": round(med_noise, 2),
            "baseline_ela_energy": round(med_ela, 2)
        }

    def _extract_bounding_boxes(
        self,
        heatmap: np.ndarray,
        patches: List[Dict[str, Any]],
        width: int,
        height: int,
        orig_w: int,
        orig_h: int,
        max_anomaly: float
    ) -> List[Dict[str, Any]]:
        """
        Clusters contiguous anomalous patches into structured bounding box regions.
        """
        # Threshold for localized anomaly flag
        threshold = max(0.35, min(0.85, max_anomaly * 0.75))
        if max_anomaly < 0.35:
            # Entire image is uniformly low anomaly
            return []

        anomalous_patches = [p for p in patches if p.get("anomaly_score", 0) >= threshold]
        if not anomalous_patches:
            return []

        # Simple spatial clustering for bounding box aggregation
        # Group overlapping or nearby patches
        clusters: List[List[Dict[str, Any]]] = []
        for p in anomalous_patches:
            placed = False
            py, px, py2, px2 = p["box"]
            for c in clusters:
                # Check if patch overlaps or is close to existing cluster
                cy = min(item["box"][0] for item in c)
                cx = min(item["box"][1] for item in c)
                cy2 = max(item["box"][2] for item in c)
                cx2 = max(item["box"][3] for item in c)

                # Expansion buffer
                margin = (py2 - py) // 2
                if not (px2 + margin < cx or px - margin > cx2 or py2 + margin < cy or py - margin > cy2):
                    c.append(p)
                    placed = True
                    break
            if not placed:
                clusters.append([p])

        regions: List[Dict[str, Any]] = []
        for cluster in clusters[:3]:  # Top 3 most distinct clusters
            cy = min(p["box"][0] for p in cluster)
            cx = min(p["box"][1] for p in cluster)
            cy2 = max(p["box"][2] for p in cluster)
            cx2 = max(p["box"][3] for p in cluster)

            cluster_scores = [p["anomaly_score"] for p in cluster]
            avg_score = float(np.mean(cluster_scores))
            peak_score = float(np.max(cluster_scores))

            # Semantic region labeling
            center_x = (cx + cx2) / 2.0 / max(1, width)
            center_y = (cy + cy2) / 2.0 / max(1, height)

            if 0.25 <= center_x <= 0.75 and 0.20 <= center_y <= 0.55:
                semantic_label = "Eyewear / Facial Region"
            elif center_y < 0.40:
                semantic_label = "Upper ROI"
            elif center_y > 0.65:
                semantic_label = "Lower ROI"
            elif center_x < 0.35:
                semantic_label = "Left ROI"
            elif center_x > 0.65:
                semantic_label = "Right ROI"
            else:
                semantic_label = "Central Subject ROI"

            # Primary signal attribution
            avg_noise = float(np.mean([p["noise_var"] for p in cluster]))
            avg_ela = float(np.mean([p["ela_energy"] for p in cluster]))
            if avg_noise > avg_ela * 1.5:
                primary_anomaly = "Sensor Noise Inconsistency"
            elif avg_ela > 20.0:
                primary_anomaly = "Localized Compression Discrepancy"
            else:
                primary_anomaly = "Boundary Resampling Discontinuity"

            inv_scale_x = orig_w / max(1, width)
            inv_scale_y = orig_h / max(1, height)

            regions.append({
                "region_id": f"ROI-{len(regions) + 1}",
                "semantic_label": semantic_label,
                "primary_anomaly": primary_anomaly,
                "anomaly_score": round(peak_score * 100.0, 1),
                "confidence": round(min(0.95, avg_score + 0.15), 2),
                "bounding_box": {
                    "ymin": round(cy / height, 3),
                    "xmin": round(cx / width, 3),
                    "ymax": round(cy2 / height, 3),
                    "xmax": round(cx2 / width, 3),
                    "pixel_coords": [int(cx * inv_scale_x), int(cy * inv_scale_y), int(cx2 * inv_scale_x), int(cy2 * inv_scale_y)]
                }
            })

        return regions

    def _save_heatmap_image(
        self,
        heatmap: np.ndarray,
        original_img: Image.Image,
        evidence_id: str
    ) -> Optional[Path]:
        """
        Blends the spatial anomaly heatmap with the original image using a high-contrast
        forensic colormap (Navy -> Cyan -> Yellow -> Crimson Red).
        """
        try:
            h, w = heatmap.shape
            # Normalize to 0-255
            norm_heat = np.clip(heatmap * 255.0, 0, 255).astype(np.uint8)

            # High-contrast forensic color palette
            # Low: Dark Navy/Slate (0, 20, 50)
            # Med: Cyan / Electric Yellow (0, 220, 255 -> 255, 220, 0)
            # High: Bright Crimson Red (255, 20, 50)
            rgb_heat = np.zeros((h, w, 3), dtype=np.uint8)

            # Vectorized piecewise colormapping
            val = norm_heat.astype(np.float32) / 255.0
            
            # Red channel
            rgb_heat[..., 0] = np.clip(
                np.where(val < 0.5, val * 2.0 * 50.0, 50.0 + (val - 0.5) * 2.0 * 205.0),
                0, 255
            ).astype(np.uint8)

            # Green channel
            rgb_heat[..., 1] = np.clip(
                np.where(val < 0.5, val * 2.0 * 200.0, 200.0 - (val - 0.5) * 2.0 * 180.0),
                0, 255
            ).astype(np.uint8)

            # Blue channel
            rgb_heat[..., 2] = np.clip(
                np.where(val < 0.5, 120.0 + (1.0 - val * 2.0) * 100.0, (1.0 - (val - 0.5) * 2.0) * 80.0),
                0, 255
            ).astype(np.uint8)

            heat_pil = Image.fromarray(rgb_heat).resize(original_img.size, Image.Resampling.BILINEAR)
            base_rgb = original_img.convert("RGB")
            blended = Image.blend(base_rgb, heat_pil, alpha=0.55)

            out_dir = FORENSIC_DIR
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"manipulation_heatmap_{evidence_id}.png"
            blended.save(out_path, format="PNG")
            return out_path
        except Exception as e:
            return None
