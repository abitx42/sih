"""
Adversarial Robustness Stress Tester
Tests whether a forensic conclusion survives common real-world image transformations.
All transforms are in-memory — original stored files are never modified.
"""
import io
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

TRANSFORMS = [
    {"key": "original",               "label": "Original",                   "desc": "Unmodified baseline"},
    {"key": "jpeg_90",                "label": "JPEG 90%",                   "desc": "Light recompression (social share)"},
    {"key": "jpeg_70",                "label": "JPEG 70%",                   "desc": "Moderate lossy compression"},
    {"key": "resize_75",              "label": "Resize 75%",                 "desc": "Downscale to 75%"},
    {"key": "blur",                   "label": "Gaussian Blur σ=1.5",        "desc": "Smoothing / anti-forensics"},
    {"key": "sharpen",                "label": "Sharpen",                    "desc": "Sharpening post-process"},
    {"key": "screenshot_sim",         "label": "Screenshot Simulation",      "desc": "JPEG 80% + slight brightness shift"},
    {"key": "social_media",           "label": "Social Media Compression",   "desc": "JPEG 55% + minor resize"},
]


class RobustnessTester:
    """
    Applies a standardized set of image transforms and re-evaluates key forensic
    signals (Frequency Domain + Synthetic Noise specialists only — fast, CPU-only).
    The original evidence file is never modified.
    """

    @staticmethod
    def run(file_path: Path, evidence_id: str, original_verdict: str, original_score: float) -> Dict[str, Any]:
        """
        Run the robustness battery on the given image file.
        Returns a structured result dict with per-transform outcomes.
        """
        try:
            from PIL import Image, ImageFilter
            import numpy as np
            from scipy import ndimage
        except ImportError as e:
            return {"error": f"Dependency unavailable: {e}", "transforms": []}

        try:
            base_img = Image.open(file_path).convert("RGB")
        except Exception as e:
            return {"error": f"Could not open image: {type(e).__name__}", "transforms": []}

        results = []

        for tf in TRANSFORMS:
            t_start = time.time()
            try:
                img = RobustnessTester._apply_transform(base_img, tf["key"])
                img_arr = np.array(img, dtype=np.float32)

                # Fast frequency + noise analysis (no ML)
                fft_score = RobustnessTester._fft_score(img_arr)
                noise_score = RobustnessTester._noise_score(img_arr)
                composite = (fft_score * 0.5 + noise_score * 0.5)

                if composite >= 60.0:
                    verdict = "MANIPULATED"
                    verdict_icon = "✅"
                elif composite >= 35.0:
                    verdict = "REVIEW REQUIRED"
                    verdict_icon = "⚠️"
                else:
                    verdict = "INCONCLUSIVE"
                    verdict_icon = "❌"

                latency_ms = round((time.time() - t_start) * 1000, 1)
                results.append({
                    "key": tf["key"],
                    "label": tf["label"],
                    "description": tf["desc"],
                    "fft_score": round(fft_score, 1),
                    "noise_score": round(noise_score, 1),
                    "composite_score": round(composite, 1),
                    "verdict": verdict,
                    "verdict_icon": verdict_icon,
                    "consistent_with_original": verdict == original_verdict or (verdict == "REVIEW REQUIRED" and original_verdict in ("REVIEW REQUIRED", "MANIPULATED")),
                    "latency_ms": latency_ms,
                    "error": None
                })
            except Exception as e:
                latency_ms = round((time.time() - t_start) * 1000, 1)
                results.append({
                    "key": tf["key"],
                    "label": tf["label"],
                    "description": tf["desc"],
                    "verdict": "ERROR",
                    "verdict_icon": "⚠️",
                    "consistent_with_original": False,
                    "latency_ms": latency_ms,
                    "error": type(e).__name__
                })

        # Summary stats
        consistent_count = sum(1 for r in results if r.get("consistent_with_original"))
        total = len(results)
        robustness_pct = round(consistent_count / max(total, 1) * 100.0, 1)

        return {
            "evidence_id": evidence_id,
            "original_verdict": original_verdict,
            "original_score": original_score,
            "total_transforms": total,
            "consistent_transforms": consistent_count,
            "robustness_percentage": robustness_pct,
            "robustness_label": (
                "HIGH ROBUSTNESS" if robustness_pct >= 75.0 else
                "MODERATE ROBUSTNESS" if robustness_pct >= 50.0 else
                "LOW ROBUSTNESS"
            ),
            "transforms": results,
            "disclaimer": (
                "Robustness testing evaluates frequency-domain and noise-residual signals only. "
                "Results indicate signal persistence under transformation — not absolute authenticity."
            )
        }

    @staticmethod
    def _apply_transform(img, key: str):
        from PIL import Image, ImageFilter, ImageEnhance
        import io

        if key == "original":
            return img.copy()
        elif key == "jpeg_90":
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            buf.seek(0)
            return Image.open(buf).convert("RGB")
        elif key == "jpeg_70":
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            buf.seek(0)
            return Image.open(buf).convert("RGB")
        elif key == "resize_75":
            w, h = img.size
            resized = img.resize((int(w * 0.75), int(h * 0.75)), Image.LANCZOS)
            buf = io.BytesIO()
            resized.save(buf, format="JPEG", quality=95)
            buf.seek(0)
            return Image.open(buf).convert("RGB").resize((w, h), Image.LANCZOS)
        elif key == "blur":
            return img.filter(ImageFilter.GaussianBlur(radius=1.5))
        elif key == "sharpen":
            return img.filter(ImageFilter.SHARPEN)
        elif key == "screenshot_sim":
            enhancer = ImageEnhance.Brightness(img)
            brightened = enhancer.enhance(1.05)
            buf = io.BytesIO()
            brightened.save(buf, format="JPEG", quality=80)
            buf.seek(0)
            return Image.open(buf).convert("RGB")
        elif key == "social_media":
            w, h = img.size
            sm = img.resize((int(w * 0.9), int(h * 0.9)), Image.LANCZOS)
            buf = io.BytesIO()
            sm.save(buf, format="JPEG", quality=55)
            buf.seek(0)
            return Image.open(buf).convert("RGB").resize((w, h), Image.LANCZOS)
        else:
            return img.copy()

    @staticmethod
    def _fft_score(img_arr) -> float:
        """Fast 2D FFT anomaly score."""
        import numpy as np
        try:
            gray = img_arr.mean(axis=2)
            fft = np.fft.fft2(gray)
            fft_shift = np.fft.fftshift(fft)
            magnitude = np.log1p(np.abs(fft_shift))
            h, w = magnitude.shape
            # High-frequency power
            center_mask = np.zeros((h, w), dtype=bool)
            ch, cw = h // 2, w // 2
            r = min(ch, cw) // 3
            Y, X = np.ogrid[:h, :w]
            center_mask[(Y - ch) ** 2 + (X - cw) ** 2 <= r ** 2] = True
            hf_power = magnitude[~center_mask].mean()
            total_power = magnitude.mean()
            ratio = hf_power / max(total_power, 1e-6)
            # Typical AI images: ratio > 0.85
            return min(100.0, max(0.0, (ratio - 0.7) / 0.3 * 100.0))
        except Exception:
            return 0.0

    @staticmethod
    def _noise_score(img_arr) -> float:
        """Fast PRNU noise residual anomaly score."""
        import numpy as np
        try:
            from scipy import ndimage
            gray = img_arr.mean(axis=2)
            smooth = ndimage.gaussian_filter(gray.astype(float), sigma=3.0)
            residual = gray.astype(float) - smooth
            variance = float(np.var(residual))
            # Very low variance → synthetic / over-smoothed
            if variance < 25.0:
                return min(100.0, (25.0 - variance) / 25.0 * 80.0)
            return 0.0
        except Exception:
            return 0.0
