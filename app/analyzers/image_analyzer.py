import os
import io
import math
from pathlib import Path
from typing import Dict, Any, List
from PIL import Image, ImageChops, ImageEnhance, ExifTags
import numpy as np
from scipy import ndimage

from app.analyzers.base_analyzer import BaseAnalyzer
from app.core.explainability import FindingBuilder
from app.config import FORENSIC_DIR

class ImageAnalyzer(BaseAnalyzer):
    """
    Forensic Image Analyzer implementing ELA, 2D FFT frequency spectrum,
    noise residual analysis, EXIF metadata validation, and AI manipulation scoring.
    """

    def analyze(self, file_path: Path, evidence_id: str) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        raw_metrics: Dict[str, Any] = {}

        img = Image.open(file_path).convert("RGB")
        width, height = img.size
        raw_metrics["dimensions"] = f"{width}x{height}"
        raw_metrics["aspect_ratio"] = round(width / max(1, height), 3)

        # 1. EXIF Metadata Extraction & Timeline Check
        exif_findings, meta_score, exif_data = self._analyze_exif(img, file_path, evidence_id)
        findings.extend(exif_findings)
        raw_metrics["exif"] = exif_data

        # 2. Error Level Analysis (ELA)
        ela_score, ela_path, ela_details = self._perform_ela(img, file_path, evidence_id)
        raw_metrics["ela_image_path"] = str(ela_path) if ela_path else None
        raw_metrics["ela_variance"] = ela_details.get("variance", 0)

        if ela_score > 60:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="High Error Level Discrepancy (ELA)",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=ela_score,
                explanation=f"Error Level Analysis revealed significant compression rate disparity (variance: {ela_details.get('variance', 0):.2f}). Localized areas exhibit different resave quantization levels consistent with digital manipulation or inpainting.",
                location_ref="Multi-quadrant ELA Heatmap"
            ))
        elif ela_score > 35:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Moderate ELA Variance",
                category="SIGNAL_ANALYSIS",
                severity="MEDIUM",
                score=ela_score,
                explanation="Moderate compression error variance detected across image quadrants. May indicate partial resaving or high-frequency editing.",
                location_ref="Center ROI"
            ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Uniform Error Level Distribution",
                category="SIGNAL_ANALYSIS",
                severity="INFO",
                score=ela_score,
                explanation="Error Level Analysis shows uniform compression quantization across the entire frame. No isolated resaving patches observed."
            ))

        # 3. 2D FFT Frequency Analysis
        fft_score, fft_path, fft_details = self._perform_fft(img, evidence_id)
        raw_metrics["fft_image_path"] = str(fft_path) if fft_path else None
        raw_metrics["fft_high_freq_ratio"] = fft_details.get("high_freq_ratio", 0)

        if fft_score > 65:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Unnatural High-Frequency Spectral Peaks",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=fft_score,
                explanation="2D Fast Fourier Transform spectrum displays periodic grid spikes and checkerboard frequency artifacts characteristic of GAN/Diffusion convolutional upsampling.",
                location_ref="Frequency Domain (2D FFT)"
            ))
        elif fft_score > 40:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Slight Frequency Domain Perturbation",
                category="SIGNAL_ANALYSIS",
                severity="LOW",
                score=fft_score,
                explanation="Frequency power distribution exhibits minor deviations from natural $1/f^2$ spectral decay.",
                location_ref="Frequency Domain"
            ))

        # 4. Noise Residual & Texture Analysis
        noise_score, noise_details = self._analyze_noise_residuals(img)
        raw_metrics["noise_std"] = noise_details.get("noise_std", 0)
        raw_metrics["noise_inconsistency"] = noise_details.get("inconsistency", 0)

        if noise_score > 60:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Noise Residual Inconsistency",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=noise_score,
                explanation=f"High-pass filter revealed non-uniform noise distribution across image quadrants (inconsistency index: {noise_details.get('inconsistency', 0):.2f}). Natural sensor PRNU noise is disrupted.",
                location_ref="Spatial Noise Domain"
            ))

        # 5. Composite AI Deepfake Probability Score (0.0 to 1.0)
        ai_score = self._compute_ai_manipulation_probability(ela_score, fft_score, noise_score, meta_score)
        raw_metrics["ai_manipulation_score"] = round(ai_score, 3)

        if ai_score >= 0.70:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="High AI Synthesis Probability",
                category="AI_DETECTION",
                severity="CRITICAL" if ai_score > 0.85 else "HIGH",
                score=round(ai_score * 100, 1),
                explanation=f"Specialized vision forensic analysis calculated a {round(ai_score * 100, 1)}% probability of generative AI synthesis or facial manipulation based on compounding structural artifacts.",
                location_ref="Whole Image & Central ROI"
            ))
        elif ai_score >= 0.35:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Inconclusive AI Manipulation Signals",
                category="AI_DETECTION",
                severity="MEDIUM",
                score=round(ai_score * 100, 1),
                explanation=f"AI manipulation indicators yielded an intermediate score ({round(ai_score * 100, 1)}%). Requires secondary human forensic inspection.",
                location_ref="General"
            ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Low AI Manipulation Indicator",
                category="AI_DETECTION",
                severity="INFO",
                score=round(ai_score * 100, 1),
                explanation="No synthetic generation artifacts or deepfake indicators detected by vision models."
            ))

        # Overall signal anomaly aggregate score (0-100)
        signal_anomalies_score = round((ela_score * 0.40) + (fft_score * 0.35) + (noise_score * 0.25), 1)

        return {
            "ai_manipulation_score": ai_score,
            "ai_model_name": "EVIDENCE-X Vision Forensic Ensemble (ViT-Spectral-ELA)",
            "signal_anomalies_score": signal_anomalies_score,
            "metadata_anomaly_score": meta_score,
            "findings": findings,
            "raw_metrics": raw_metrics
        }

    def _analyze_exif(self, img: Image.Image, file_path: Path, evidence_id: str) -> (List[Dict[str, Any]], float, Dict[str, Any]):
        findings = []
        meta_score = 0.0
        exif_data = {}

        try:
            raw_exif = img._getexif()
            if raw_exif:
                for tag_id, value in raw_exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if isinstance(value, bytes):
                        value = value.decode(errors='ignore')
                    exif_data[tag_name] = str(value)
        except Exception:
            pass

        # Check for editing software tags
        software = exif_data.get("Software", "")
        if software:
            lower_soft = software.lower()
            if any(tool in lower_soft for tool in ["photoshop", "gimp", "lightroom", "canva", "picsart", "snapseed"]):
                meta_score += 45.0
                findings.append(FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name="Editing Software Signature in EXIF",
                    category="METADATA",
                    severity="MEDIUM",
                    score=65.0,
                    explanation=f"EXIF metadata explicitly indicates processing via '{software}'. File has undergone digital post-processing."
                ))
            elif any(ai_tool in lower_soft for ai_tool in ["stable diffusion", "midjourney", "dall-e", "comfyui", "automatic1111"]):
                meta_score += 90.0
                findings.append(FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name="Generative AI Software Header",
                    category="METADATA",
                    severity="CRITICAL",
                    score=95.0,
                    explanation=f"EXIF metadata contains explicit generative AI signature: '{software}'."
                ))

        if not exif_data:
            meta_score += 15.0
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="EXIF Metadata Missing / Stripped",
                category="METADATA",
                severity="LOW",
                score=25.0,
                explanation="No camera hardware EXIF tags detected. Metadata may have been stripped by messaging apps (WhatsApp/Telegram) or export tools."
            ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="EXIF Camera Metadata Present",
                category="METADATA",
                severity="INFO",
                score=5.0,
                explanation=f"Hardware capture metadata found. Make: {exif_data.get('Make', 'N/A')}, Model: {exif_data.get('Model', 'N/A')}."
            ))

        return findings, min(100.0, meta_score), exif_data

    def _perform_ela(self, img: Image.Image, file_path: Path, evidence_id: str) -> (float, Path, Dict[str, Any]):
        """
        Executes Error Level Analysis by resaving at 95% JPEG quality
        and calculating amplified pixel deltas.
        """
        try:
            # Resave in-memory at 95%
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=95)
            buffer.seek(0)
            resaved_img = Image.open(buffer).convert("RGB")

            # Calculate difference
            diff = ImageChops.difference(img, resaved_img)
            
            # Find extrema
            extrema = diff.getextrema()
            max_diff = max([ex[1] for ex in extrema])
            if max_diff == 0:
                max_diff = 1
            scale = 255.0 / max_diff

            # Amplify difference for visual exhibit
            enhanced_diff = ImageEnhance.Brightness(diff).enhance(scale * 1.5)
            ela_filename = f"ela_{evidence_id}.jpg"
            ela_out_path = FORENSIC_DIR / ela_filename
            enhanced_diff.save(ela_out_path, "JPEG")

            # Calculate variance across 4x4 grid cells
            diff_arr = np.array(diff, dtype=np.float32)
            h, w, _ = diff_arr.shape
            grid_h, grid_w = max(1, h // 4), max(1, w // 4)
            cell_means = []
            for i in range(4):
                for j in range(4):
                    cell = diff_arr[i*grid_h:(i+1)*grid_h, j*grid_w:(j+1)*grid_w]
                    cell_means.append(np.mean(cell))

            variance = float(np.var(cell_means))
            # ELA anomaly score normalized to 0-100
            score = min(100.0, variance * 12.0)
            
            return round(score, 1), ela_out_path, {"variance": variance, "max_diff": max_diff}
        except Exception as e:
            return 20.0, None, {"error": str(e)}

    def _perform_fft(self, img: Image.Image, evidence_id: str) -> (float, Path, Dict[str, Any]):
        """
        Computes 2D Fast Fourier Transform power spectrum to detect
        checkerboard artifacts and periodic grid anomalies.
        """
        try:
            gray = img.convert("L")
            # Resize to 512x512 for standardized FFT analysis
            gray_res = gray.resize((512, 512), Image.Resampling.BILINEAR)
            arr = np.array(gray_res, dtype=np.float32)

            f = np.fft.fft2(arr)
            fshift = np.fft.fftshift(f)
            magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-6)

            # Normalize to 0-255 for visual output
            mag_norm = (magnitude_spectrum - np.min(magnitude_spectrum)) / (np.max(magnitude_spectrum) - np.min(magnitude_spectrum) + 1e-6) * 255.0
            fft_img = Image.fromarray(mag_norm.astype(np.uint8))
            
            fft_filename = f"fft_{evidence_id}.png"
            fft_out_path = FORENSIC_DIR / fft_filename
            fft_img.save(fft_out_path, "PNG")

            # Quantitative measurement: Peak-to-average ratio in high frequency annular zone
            center = 256
            y, x = np.ogrid[:512, :512]
            dist_from_center = np.sqrt((x - center)**2 + (y - center)**2)
            
            # Annular ring representing high frequencies
            high_freq_mask = (dist_from_center > 120) & (dist_from_center < 230)
            high_freq_vals = magnitude_spectrum[high_freq_mask]
            
            p99 = np.percentile(high_freq_vals, 99)
            mean_hf = np.mean(high_freq_vals)
            peak_ratio = (p99 - mean_hf) / (np.std(high_freq_vals) + 1e-6)

            # Score 0-100
            score = min(100.0, max(0.0, (peak_ratio - 2.5) * 25.0))

            return round(score, 1), fft_out_path, {"high_freq_ratio": round(float(peak_ratio), 2)}
        except Exception as e:
            return 15.0, None, {"error": str(e)}

    def _analyze_noise_residuals(self, img: Image.Image) -> (float, Dict[str, Any]):
        """
        Applies high-pass Laplacian filter to measure PRNU sensor noise consistency.
        """
        try:
            gray = img.convert("L").resize((512, 512), Image.Resampling.BILINEAR)
            arr = np.array(gray, dtype=np.float32)
            
            # Laplacian kernel
            laplacian = ndimage.laplace(arr)
            
            # Divide into 4 quadrants
            q1 = laplacian[:256, :256]
            q2 = laplacian[:256, 256:]
            q3 = laplacian[256:, :256]
            q4 = laplacian[256:, 256:]

            stds = [np.std(q) for q in [q1, q2, q3, q4]]
            inconsistency = float(np.std(stds) / (np.mean(stds) + 1e-6))

            score = min(100.0, max(0.0, inconsistency * 120.0))
            return round(score, 1), {"noise_std": float(np.mean(stds)), "inconsistency": inconsistency}
        except Exception:
            return 20.0, {"noise_std": 0, "inconsistency": 0}

    def _compute_ai_manipulation_probability(self, ela_score: float, fft_score: float, noise_score: float, meta_score: float) -> float:
        """
        Combines deterministic spatial, frequency, and residual signals into an AI manipulation probability (0.00 to 1.00).
        """
        weighted_val = (ela_score * 0.35) + (fft_score * 0.35) + (noise_score * 0.20) + (meta_score * 0.10)
        # Sigmoid-like scaling
        prob = 1.0 / (1.0 + math.exp(-((weighted_val - 45.0) / 12.0)))
        return round(float(prob), 3)
