import os
import io
import math
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image, ImageChops, ImageEnhance, ExifTags, ImageFilter
import numpy as np
from scipy import ndimage

from app.analyzers.base_analyzer import BaseAnalyzer
from app.analyzers.hf_image_detector import HFImageDetector
from app.analyzers.patch_localizer import PatchLocalizer
from app.core.explainability import FindingBuilder
from app.config import FORENSIC_DIR

class ImageAnalyzer(BaseAnalyzer):
    """
    Forensic Image Analyzer — v2.0 (5-signal heuristic + DIRE + 5-model ensemble + multi-resolution)
    Combines:
    1. Heuristic Forensic Anomaly Pipeline: ELA (95%), 2D FFT Frequency Analysis,
       PRNU Noise Residual Consistency, Chromatic Aberration, Bayer CFA analysis.
    2. DIRE Approximation: DCT-based Diffusion Reconstruction Error (most powerful signal
       for diffusion-generated images: Flux, SDXL, Midjourney v6, DALL-E 3).
    3. Multi-Resolution Neural Inference: global + 4 corner crops + center crop,
       aggregated to catch both global synthesis and localized AI inpainting.
    4. 5-Model Neural Vision Ensemble (Smogy, Organika, dima806 ai_vs_real,
       umm-maybe, dima806 deepfake) with calibrated weighted median fusion.
    5. Spatial Patch Localizer: Sliding ROI decomposition for localized tampering.
    6. EXIF AI Metadata: Extended detection covering ComfyUI, Firefly, Fooocus,
       SD PNG text chunks, and 20+ AI tool signatures.
    """

    def __init__(self):
        self.hf_detector = HFImageDetector()
        self.patch_localizer = PatchLocalizer()
        self._dire_analyzer = None

    def _get_dire(self):
        """Lazy-load DIREAnalyzer to avoid import errors if unavailable."""
        if self._dire_analyzer is None:
            try:
                from app.analyzers.dire_analyzer import DIREAnalyzer
                self._dire_analyzer = DIREAnalyzer()
            except Exception:
                pass
        return self._dire_analyzer

    def analyze(self, file_path: Path, evidence_id: str) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        raw_metrics: Dict[str, Any] = {}

        img = Image.open(file_path).convert("RGB")
        width, height = img.size
        raw_metrics["dimensions"] = f"{width}x{height}"
        raw_metrics["aspect_ratio"] = round(width / max(1, height), 3)

        # -------------------------------------------------------------
        # 1. HEURISTIC FORENSIC SIGNALS
        # -------------------------------------------------------------

        # A. EXIF Metadata Extraction & Timeline Check
        exif_findings, meta_score, exif_data = self._analyze_exif(img, file_path, evidence_id)
        findings.extend(exif_findings)
        raw_metrics["exif"] = exif_data

        # B. Error Level Analysis (ELA)
        ela_score, ela_path, ela_details, enhanced_diff = self._perform_ela(img, file_path, evidence_id)
        raw_metrics["ela_image_path"] = str(ela_path) if ela_path else None
        raw_metrics["ela_variance"] = ela_details.get("variance", 0)

        if ela_score > 60:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="High Error Level Discrepancy (ELA)",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=ela_score,
                explanation=f"Error Level Analysis revealed significant compression rate disparity (variance: {ela_details.get('variance', 0):.2f}). Localized areas exhibit different resave quantization levels consistent with digital editing or inpainting.",
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

        # C. 2D FFT Frequency Analysis
        fft_score, fft_path, fft_details = self._perform_fft(img, evidence_id)
        raw_metrics["fft_image_path"] = str(fft_path) if fft_path else None
        raw_metrics["fft_high_freq_ratio"] = fft_details.get("high_freq_ratio", 0)

        if fft_score > 70:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Unnatural High-Frequency Spectral Peaks",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=fft_score,
                explanation="2D Fast Fourier Transform spectrum displays periodic grid spikes and checkerboard frequency artifacts characteristic of generative convolutional upsampling.",
                location_ref="Frequency Domain (2D FFT)"
            ))
        elif fft_score > 45:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Slight Frequency Domain Perturbation",
                category="SIGNAL_ANALYSIS",
                severity="LOW",
                score=fft_score,
                explanation="Frequency power distribution exhibits minor deviations from natural spectral decay.",
                location_ref="Frequency Domain"
            ))

        # D. Noise Residual & PRNU Texture Analysis
        noise_score, noise_details = self._analyze_noise_residuals(img)
        raw_metrics["noise_std"] = noise_details.get("noise_std", 0)
        raw_metrics["noise_inconsistency"] = noise_details.get("inconsistency", 0)

        if noise_score > 60:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Sensor-Noise Consistency Heuristic: Disrupted Pattern",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=noise_score,
                explanation=f"High-pass filter revealed non-uniform noise distribution across image quadrants (inconsistency index: {noise_details.get('inconsistency', 0):.2f}). Spatial high-frequency noise variation detected (heuristic screening signal, not camera attribution).",
                location_ref="Spatial Noise Domain"
            ))

        # E. Optical Lens Chromatic Aberration (CA) Radial Dispersion
        ca_score, ca_details = self._analyze_chromatic_aberration(img)
        raw_metrics["chromatic_aberration_score"] = ca_score
        raw_metrics["ca_radial_dispersion"] = ca_details.get("radial_dispersion", 0.0)

        if ca_score > 65:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Non-Optical Color Alignment (Zero/Irregular Lens Dispersion)",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=ca_score,
                explanation="Physical camera lenses exhibit radial chromatic aberration (R-B color channel fringing increasing away from optical center). This exhibit shows synthetic non-optical alignment characteristic of generative rendering.",
                location_ref="Optical Color Channels (R-G-B)"
            ))

        # F. Bayer CFA Demosaicing Inconsistency
        cfa_score, cfa_details = self._analyze_cfa_periodicity(img)
        raw_metrics["cfa_anomaly_score"] = cfa_score
        raw_metrics["cfa_periodicity_ratio"] = cfa_details.get("periodicity_ratio", 0.0)

        # G. Spatial Patch Analysis & Localized Manipulation Localization
        patch_res = self.patch_localizer.analyze_patches(img, enhanced_diff, evidence_id)
        raw_metrics["manipulation_heatmap_path"] = patch_res.get("heatmap_path")
        raw_metrics["localized_regions"] = patch_res.get("localized_regions", [])
        raw_metrics["max_patch_anomaly"] = patch_res.get("max_patch_anomaly", 0.0)
        raw_metrics["mean_patch_anomaly"] = patch_res.get("mean_patch_anomaly", 0.0)
        raw_metrics["patch_count"] = patch_res.get("patch_count", 0)

        localized_regions = patch_res.get("localized_regions", [])
        if localized_regions:
            for r in localized_regions:
                box = r.get("bounding_box", {})
                findings.append(FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name=f"Localized Manipulation Detected ({r['semantic_label']})",
                    category="LOCALIZED_MANIPULATION",
                    severity="CRITICAL" if r["anomaly_score"] > 80.0 else "HIGH",
                    score=r["anomaly_score"],
                    explanation=f"Spatial patch analysis detected a concentrated anomaly in the {r['semantic_label']} (Score: {r['anomaly_score']:.1f}%). Primary indicator: {r['primary_anomaly']}. Significant deviation from surrounding photographic characteristics suggests localized digital modification, inpainting, or synthetic addition (e.g. eyewear, face edit, or object grafting).",
                    location_ref=f"ROI [{r['region_id']}: y:{box.get('ymin')}-{box.get('ymax')}, x:{box.get('xmin')}-{box.get('xmax')}]"
                ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Uniform Spatial Patch Consistency",
                category="SIGNAL_ANALYSIS",
                severity="INFO",
                score=patch_res.get("mean_patch_anomaly", 0.0),
                explanation="Patch-level spatial analysis shows uniform sensor noise, consistent error level, and seamless boundary gradients across all sub-regions. No isolated manipulation patches detected."
            ))

        # Comprehensive Multi-Signal Forensic Anomaly Score v2.0 (0.0 - 100.0)
        # New: DIRE gets 15% weight, replacing the weakest CFA signal (10%)
        # Weights: ELA(20) + FFT(20) + DIRE(15) + Noise(15) + CA(15) + CFA(5) + MaxPatch(10) = 100%
        max_patch_anom = patch_res.get("max_patch_anomaly", 0.0)

        # G2. DIRE Approximation — Diffusion Reconstruction Error
        dire_res = None
        dire_score_val = 0.0
        dire_available = False
        dire_analyzer = self._get_dire()
        if dire_analyzer is not None:
            try:
                dire_res = dire_analyzer.analyze(img, evidence_id)
                dire_score_val = dire_res.get("dire_score", 0.0)
                dire_available = dire_res.get("dire_status") == "AVAILABLE"
                raw_metrics["dire"] = dire_res
                if dire_available and dire_score_val > 65:
                    findings.append(FindingBuilder.create_finding(
                        evidence_id=evidence_id,
                        signal_name="DIRE: Low Diffusion Reconstruction Error",
                        category="AI_DETECTION",
                        severity="HIGH" if dire_score_val > 80 else "MEDIUM",
                        score=dire_score_val,
                        explanation=(
                            f"Diffusion Reconstruction Error approximation (DCT round-trip) yielded a DIRE score of {dire_score_val:.1f}%. "
                            "AI-generated images (Flux, SDXL, Midjourney, DALL-E) produce low reconstruction error because "
                            "diffusion sampling creates frequency-optimal images. Real photos fail the same round-trip "
                            "with higher error. This is one of the most discriminative signals for modern diffusion outputs."
                        ),
                        location_ref="DCT Frequency Domain (DIRE)"
                    ))
                elif dire_available:
                    raw_metrics["dire_note"] = f"DIRE score {dire_score_val:.1f}% — below AI-generation threshold"
            except Exception as e:
                raw_metrics["dire_error"] = str(e)

        # Composite score formula
        if dire_available:
            forensic_anomaly_score = round(
                (ela_score * 0.20) +
                (fft_score * 0.20) +
                (dire_score_val * 0.15) +
                (noise_score * 0.15) +
                (ca_score * 0.15) +
                (cfa_score * 0.05) +
                (max_patch_anom * 0.10),
                1
            )
        else:
            # Fallback without DIRE (original formula)
            forensic_anomaly_score = round(
                (ela_score * 0.20) +
                (fft_score * 0.20) +
                (noise_score * 0.15) +
                (ca_score * 0.15) +
                (cfa_score * 0.10) +
                (max_patch_anom * 0.20),
                1
            )
        raw_metrics["forensic_anomaly_score"] = forensic_anomaly_score

        # -------------------------------------------------------------
        # 2. MULTI-RESOLUTION ML INFERENCE (Global + Crops)
        # -------------------------------------------------------------
        # Step 1: Global inference on full image
        ml_result = self.hf_detector.predict(img)
        global_indicator = ml_result.get("ai_manipulation_indicator")

        # Step 2: Multi-resolution crop inference (only if image is large enough)
        # For images >= 512x512, also run 4 corner crops + center crop at 512x512
        # This catches localized AI inpainting that global inference may miss
        crop_indicators = []
        if width >= 512 and height >= 512 and global_indicator is not None:
            try:
                crop_size = min(512, width // 2, height // 2)
                crops = [
                    img.crop((0, 0, crop_size, crop_size)),                           # top-left
                    img.crop((width - crop_size, 0, width, crop_size)),               # top-right
                    img.crop((0, height - crop_size, crop_size, height)),             # bottom-left
                    img.crop((width - crop_size, height - crop_size, width, height)), # bottom-right
                    img.crop(((width - crop_size) // 2, (height - crop_size) // 2,   # center
                              (width + crop_size) // 2, (height + crop_size) // 2)),
                ]
                for crop_img in crops:
                    try:
                        crop_res = self.hf_detector.predict(crop_img)
                        crop_ind = crop_res.get("ai_manipulation_indicator")
                        if crop_ind is not None and crop_res.get("model_status") == "AVAILABLE":
                            crop_indicators.append(crop_ind)
                    except Exception:
                        continue
            except Exception:
                pass

        # Step 3: Fuse global + crop indicators
        # If any crop exceeds 0.75 (strong localized AI signal), use max(global, max_crop * 0.85)
        # Otherwise use global result unchanged
        fused_indicator = global_indicator
        if crop_indicators and global_indicator is not None:
            max_crop = max(crop_indicators)
            if max_crop >= 0.75:
                fused_indicator = round(max(global_indicator, max_crop * 0.85), 4)
                raw_metrics["multi_resolution_boost"] = True
                raw_metrics["max_crop_indicator"] = round(max_crop, 4)
            elif max_crop >= 0.55 and global_indicator < 0.50:
                # Crop found something the global missed — soft boost
                fused_indicator = round((global_indicator * 0.65) + (max_crop * 0.35), 4)
                raw_metrics["multi_resolution_soft_boost"] = True
            raw_metrics["crop_indicators"] = [round(c, 3) for c in crop_indicators]

        # Apply fused indicator back to ml_result for downstream use
        if fused_indicator is not None and fused_indicator != global_indicator:
            ml_result = dict(ml_result)
            ml_result["ai_manipulation_indicator"] = fused_indicator
            ml_result["multi_resolution_fused"] = True

        raw_metrics["ml_detector"] = ml_result

        model_status = ml_result["model_status"]
        ai_indicator = ml_result["ai_manipulation_indicator"]
        model_conf = ml_result["model_confidence"]
        model_name = ml_result["ai_model_name"]
        model_ver = ml_result["ai_model_version"]

        if model_status == "AVAILABLE" and ai_indicator is not None:
            pct_val = round(ai_indicator * 100, 1)
            conf_pct = round(model_conf * 100, 1) if model_conf else 0
            if ai_indicator >= 0.70:
                findings.append(FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name=f"ML Vision Classifier Flag ({model_name})",
                    category="AI_DETECTION",
                    severity="CRITICAL" if ai_indicator > 0.85 else "HIGH",
                    score=pct_val,
                    explanation=f"Local Vision Transformer classifier ({model_name} rev:{model_ver}) produced an AI manipulation indicator of {pct_val}% (confidence: {conf_pct}%). Note: This automated indicator is a statistical signal and not definitive proof of manipulation.",
                    location_ref="Vision Transformer Output"
                ))
            elif ai_indicator >= 0.35:
                findings.append(FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name=f"ML Vision Classifier Intermediate ({model_name})",
                    category="AI_DETECTION",
                    severity="MEDIUM",
                    score=pct_val,
                    explanation=f"Local Vision Transformer classifier yielded an intermediate AI manipulation indicator of {pct_val}% (confidence: {conf_pct}%). Requires manual forensic review.",
                    location_ref="Vision Transformer Output"
                ))
            else:
                findings.append(FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name=f"ML Vision Classifier Baseline ({model_name})",
                    category="AI_DETECTION",
                    severity="INFO",
                    score=pct_val,
                    explanation=f"Local Vision Transformer classifier indicated low probability of manipulation ({pct_val}%, confidence: {conf_pct}%)."
                ))
        elif model_status == "ANALYSIS INCONCLUSIVE":
            conf_pct = round(model_conf * 100, 1) if model_conf else 0
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name=f"ML Vision Classifier: ANALYSIS INCONCLUSIVE",
                category="AI_DETECTION",
                severity="MEDIUM",
                score=50.0,
                explanation=f"The loaded vision model's class labels could not be deterministically mapped to manipulation categories (confidence: {conf_pct}%). Statistical AI manipulation indicator is withheld.",
                location_ref="Vision Transformer Output"
            ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name=f"ML Vision Classifier: ANALYSIS UNAVAILABLE",
                category="AI_DETECTION",
                severity="MEDIUM",
                score=50.0,
                explanation=f"Local Hugging Face vision model '{model_name}' was unavailable ({ml_result.get('error_detail', 'Inference offline')}). Automated forensic assessment is grounded exclusively on physical heuristic signals (ELA, FFT, noise, metadata).",
                location_ref="Local Inference Engine"
            ))

        return {
            "ai_model_name": model_name,
            "ai_model_version": model_ver,
            "ai_manipulation_indicator": ai_indicator,
            "model_confidence": model_conf,
            "model_status": model_status,
            "forensic_anomaly_score": forensic_anomaly_score,
            "signal_anomalies_score": forensic_anomaly_score,
            "metadata_anomaly_score": meta_score,
            "max_patch_anomaly": max_patch_anom,
            "localized_regions": localized_regions,
            "manipulation_heatmap_path": patch_res.get("heatmap_path"),
            "findings": findings,
            "raw_metrics": raw_metrics
        }

    def _analyze_exif(self, img: Image.Image, file_path: Path, evidence_id: str) -> (List[Dict[str, Any]], float, Dict[str, Any]):
        findings = []
        meta_score = 0.0
        exif_data = {}

        # --- EXIF tag extraction ---
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

        # --- PNG tEXt chunk scanning (ComfyUI, Automatic1111, InvokeAI metadata) ---
        png_text_chunks = {}
        try:
            if hasattr(img, 'text') and img.text:
                png_text_chunks = dict(img.text)
        except Exception:
            pass

        # Check PNG tEXt chunks for SD/ComfyUI generative parameters
        sd_text_keys = {"parameters", "workflow", "prompt", "negative_prompt", "invokeai_metadata",
                        "invokeai_graph", "dream", "sd-metadata"}
        sd_params_keywords = ["steps:", "cfg scale:", "sampler:", "seed:", "model:", "denoising strength:",
                               "clip skip:", "hires fix:", "lora:", "controlnet:"]

        for key in sd_text_keys:
            chunk_val = png_text_chunks.get(key, "")
            if chunk_val:
                lower_val = chunk_val.lower()
                if any(kw in lower_val for kw in sd_params_keywords) or key in ("workflow", "invokeai_metadata", "invokeai_graph"):
                    meta_score = max(meta_score, 90.0)
                    exif_data[f"png_{key}"] = chunk_val[:200]
                    findings.append(FindingBuilder.create_finding(
                        evidence_id=evidence_id,
                        signal_name="Generative AI PNG Metadata Chunk Detected",
                        category="METADATA",
                        severity="CRITICAL",
                        score=95.0,
                        explanation=(
                            f"PNG tEXt chunk '{key}' contains Stable Diffusion / ComfyUI / InvokeAI generative parameters "
                            f"(Steps, CFG scale, Sampler, Seed, etc.). This image was produced by an AI image generator."
                        )
                    ))
                    break  # One finding is sufficient

        # --- Software tag: editing tools vs AI generators ---
        # Extended AI generator list (20+ tools for 2024-2025 coverage)
        _AI_GENERATORS = [
            "stable diffusion", "midjourney", "dall-e", "dalle", "comfyui",
            "automatic1111", "a1111", "invokeai", "invoke ai", "fooocus",
            "flux", "flux.1", "playground ai", "adobe firefly", "firefly",
            "microsoft designer", "bing image creator", "imagen", "ideogram",
            "lexica", "nightcafe", "dream studio", "dreamstudio",
            "canva ai", "canva magic", "adobe content credentials",
            "novelai", "novel ai", "tensor art", "civitai",
        ]
        _EDITING_TOOLS = [
            "photoshop", "gimp", "lightroom", "canva", "picsart",
            "snapseed", "capture one", "darktable", "affinity photo",
            "luminar", "on1", "dx0", "paintshop", "pixelmator",
        ]

        software = exif_data.get("Software", "")
        user_comment = exif_data.get("UserComment", "")

        # Check Software tag + UserComment for AI generator signatures
        combined_meta = (software + " " + user_comment).lower()

        if any(ai_tool in combined_meta for ai_tool in _AI_GENERATORS):
            detected_tool = next((t for t in _AI_GENERATORS if t in combined_meta), software or "AI Generator")
            meta_score = max(meta_score, 90.0)
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Generative AI Software Signature in EXIF",
                category="METADATA",
                severity="CRITICAL",
                score=95.0,
                explanation=f"EXIF metadata contains explicit generative AI software marker: '{detected_tool}'. This file was generated by an AI image synthesis tool."
            ))
        elif software and any(tool in software.lower() for tool in _EDITING_TOOLS):
            meta_score = max(meta_score, 45.0)
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Photo Editing Software Signature in EXIF",
                category="METADATA",
                severity="MEDIUM",
                score=65.0,
                explanation=f"EXIF metadata indicates post-processing via '{software}'. File has undergone digital modification in an image editing tool."
            ))

        # --- Check for missing EXIF (AI images rarely have camera EXIF) ---
        has_camera_exif = bool(exif_data.get("Make") or exif_data.get("Model") or exif_data.get("DateTimeOriginal"))
        if not exif_data and not png_text_chunks:
            meta_score = max(meta_score, 15.0)
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="EXIF Metadata Missing / Stripped",
                category="METADATA",
                severity="LOW",
                score=25.0,
                explanation="No camera hardware EXIF tags detected. Metadata may have been stripped by messaging apps, social media platforms, or export tools. AI-generated images typically lack camera EXIF entirely."
            ))
        elif has_camera_exif:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Hardware Camera EXIF Present",
                category="METADATA",
                severity="INFO",
                score=5.0,
                explanation=f"Hardware camera capture metadata found. Make: {exif_data.get('Make', 'N/A')}, Model: {exif_data.get('Model', 'N/A')}. Presence of authentic camera EXIF reduces AI-generation probability, though EXIF can be injected."
            ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Partial EXIF — No Camera Hardware Tags",
                category="METADATA",
                severity="LOW",
                score=20.0,
                explanation=f"EXIF metadata present but lacks camera hardware identifiers (Make/Model/DateTimeOriginal). Software tag: '{software or 'None'}'."
            ))

        return findings, min(100.0, meta_score), exif_data


    def _perform_ela(self, img: Image.Image, file_path: Path, evidence_id: str) -> (float, Path, Dict[str, Any]):
        try:
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=95)
            buffer.seek(0)
            resaved_img = Image.open(buffer).convert("RGB")

            diff = ImageChops.difference(img, resaved_img)
            extrema = diff.getextrema()
            max_diff = max([ex[1] for ex in extrema])
            if max_diff == 0:
                max_diff = 1
            scale = 255.0 / max_diff

            enhanced_diff = ImageEnhance.Brightness(diff).enhance(scale * 1.5)
            ela_filename = f"ela_{evidence_id}.jpg"
            ela_out_path = FORENSIC_DIR / ela_filename
            enhanced_diff.save(ela_out_path, "JPEG")

            diff_arr = np.array(diff, dtype=np.float32)
            h, w, _ = diff_arr.shape
            grid_h, grid_w = max(1, h // 4), max(1, w // 4)
            cell_means = []
            for i in range(4):
                for j in range(4):
                    cell = diff_arr[i*grid_h:(i+1)*grid_h, j*grid_w:(j+1)*grid_w]
                    cell_means.append(np.mean(cell))

            variance = float(np.var(cell_means))
            raw_score = min(100.0, variance * 12.0)

            # JPEG Discount: Real camera JPEGs inherently produce higher ELA variance
            # from natural lossy re-compression artifacts. We discount by 25% for JPEG
            # source files to reduce false positives on authentic social-media images.
            # PNG/WebP/BMP originals retain the full score.
            source_suffix = str(file_path).lower().rsplit(".", 1)[-1] if file_path else ""
            if source_suffix in ("jpg", "jpeg"):
                score = min(100.0, raw_score * 0.75)
            else:
                score = raw_score

            return round(score, 1), ela_out_path, {"variance": variance, "max_diff": max_diff, "jpeg_discount_applied": source_suffix in ("jpg", "jpeg")}, enhanced_diff
        except Exception as e:
            return 20.0, None, {"error": str(e)}, None

    def _perform_fft(self, img: Image.Image, evidence_id: str) -> (float, Path, Dict[str, Any]):
        try:
            gray = img.convert("L")
            gray_res = gray.resize((512, 512), Image.Resampling.BILINEAR)
            arr = np.array(gray_res, dtype=np.float32)

            f = np.fft.fft2(arr)
            fshift = np.fft.fftshift(f)
            magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-6)

            mag_norm = (magnitude_spectrum - np.min(magnitude_spectrum)) / (np.max(magnitude_spectrum) - np.min(magnitude_spectrum) + 1e-6) * 255.0
            fft_img = Image.fromarray(mag_norm.astype(np.uint8))
            
            fft_filename = f"fft_{evidence_id}.png"
            fft_out_path = FORENSIC_DIR / fft_filename
            fft_img.save(fft_out_path, "PNG")

            center = 256
            y, x = np.ogrid[:512, :512]
            dist_from_center = np.sqrt((x - center)**2 + (y - center)**2)
            high_freq_mask = (dist_from_center > 120) & (dist_from_center < 230)
            high_freq_vals = magnitude_spectrum[high_freq_mask]
            
            p99 = np.percentile(high_freq_vals, 99)
            mean_hf = np.mean(high_freq_vals)
            peak_ratio = (p99 - mean_hf) / (np.std(high_freq_vals) + 1e-6)

            score = min(100.0, max(0.0, (peak_ratio - 2.5) * 25.0))
            return round(score, 1), fft_out_path, {"high_freq_ratio": round(float(peak_ratio), 2)}
        except Exception as e:
            return 15.0, None, {"error": str(e)}

    def _analyze_noise_residuals(self, img: Image.Image) -> (float, Dict[str, Any]):
        try:
            gray = img.convert("L").resize((512, 512), Image.Resampling.BILINEAR)
            arr = np.array(gray, dtype=np.float32)
            
            laplacian = ndimage.laplace(arr)
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

    def _analyze_chromatic_aberration(self, img: Image.Image) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluates Optical Chromatic Aberration (CA) Radial Consistency.
        Real refractive camera lenses cause radial lateral chromatic dispersion (color shift between R and B away from optical center).
        Pure generative AI images exhibit synthetic or non-optical channel alignment.
        """
        try:
            res_img = img.resize((384, 384), Image.Resampling.BILINEAR)
            r, g, b = res_img.split()
            arr_r = np.array(r, dtype=np.float32)
            arr_g = np.array(g, dtype=np.float32)
            arr_b = np.array(b, dtype=np.float32)

            # High-pass gradient of each channel
            grad_r = np.hypot(ndimage.sobel(arr_r, axis=0), ndimage.sobel(arr_r, axis=1))
            grad_b = np.hypot(ndimage.sobel(arr_b, axis=0), ndimage.sobel(arr_b, axis=1))

            # Channel gradient difference
            diff_rb = np.abs(grad_r - grad_b)
            center = 192
            y, x = np.ogrid[:384, :384]
            radius = np.sqrt((x - center)**2 + (y - center)**2)

            center_mask = radius < 70
            corner_mask = radius > 140

            center_disp = float(np.mean(diff_rb[center_mask])) if np.any(center_mask) else 1.0
            corner_disp = float(np.mean(diff_rb[corner_mask])) if np.any(corner_mask) else 1.0

            # Radial dispersion ratio (Corner vs Center)
            radial_ratio = corner_disp / (center_disp + 1e-5)

            # In natural optical photography, radial_ratio is typically 1.2 to 2.8.
            # In synthetic/AI images, color channels are mathematically synchronized or artificially flat (ratio < 1.05 or > 4.5).
            if radial_ratio < 1.05:
                # Unnaturally uniform color alignment across radial distance
                ca_anomaly = min(100.0, (1.05 - radial_ratio) * 150.0 + 35.0)
            elif radial_ratio > 4.0:
                ca_anomaly = min(100.0, (radial_ratio - 4.0) * 20.0 + 50.0)
            else:
                ca_anomaly = max(10.0, min(35.0, abs(radial_ratio - 1.8) * 15.0))

            return round(ca_anomaly, 1), {"radial_dispersion": round(radial_ratio, 3), "corner_disp": round(corner_disp, 2), "center_disp": round(center_disp, 2)}
        except Exception as e:
            return 20.0, {"error": str(e)}

    def _analyze_cfa_periodicity(self, img: Image.Image) -> Tuple[float, Dict[str, Any]]:
        """
        Evaluates Bayer Color Filter Array (CFA) Demosaicing Residuals.
        Camera sensors interpolate color via Bayer pattern grids. Generative AI images lack physical Bayer sensor periodicity.
        """
        try:
            res_img = img.convert("L").resize((256, 256), Image.Resampling.BILINEAR)
            arr = np.array(res_img, dtype=np.float32)

            # Second-order demosaicing kernel difference: G(x,y) - [G(x-1,y)+G(x+1,y)+G(x,y-1)+G(x,y+1)]/4
            kernel = np.array([[0, 0.25, 0], [0.25, -1.0, 0.25], [0, 0.25, 0]], dtype=np.float32)
            cfa_res = ndimage.convolve(arr, kernel)

            # Check 2x2 grid variance
            q00 = cfa_res[0::2, 0::2]
            q01 = cfa_res[0::2, 1::2]
            q10 = cfa_res[1::2, 0::2]
            q11 = cfa_res[1::2, 1::2]

            var_means = [float(np.mean(np.abs(q))) for q in [q00, q01, q10, q11]]
            grid_disp = float(np.std(var_means) / (np.mean(var_means) + 1e-6))

            # Optical sensor captures display higher demosaicing periodicity variance (> 0.12)
            # Synthetic images have homogeneous interpolation (grid_disp < 0.05)
            if grid_disp < 0.05:
                cfa_score = min(100.0, (0.05 - grid_disp) * 800.0 + 40.0)
            else:
                cfa_score = max(10.0, min(30.0, (0.15 - grid_disp) * 100.0))

            return round(cfa_score, 1), {"periodicity_ratio": round(grid_disp, 4)}
        except Exception as e:
            return 20.0, {"error": str(e)}

