import time
import json
import logging
from typing import Dict, Any, List, Optional
from PIL import Image
import numpy as np
from scipy import ndimage
import requests

from app.config import settings
from app.analyzers.hf_image_detector import HFImageDetector
from app.analyzers.patch_localizer import PatchLocalizer

logger = logging.getLogger(__name__)

_hf_detector = HFImageDetector()

class BaseSpecialist:
    """
    Base class for all forensic specialists in the Truth Lens ensemble.
    """
    def __init__(self, name: str, specialist_type: str, category: str):
        self.name = name
        self.specialist_type = specialist_type
        self.category = category  # AI_MODEL, PHYSICAL_SIGNAL, PROVENANCE, EXTERNAL_API

class SpatialVisionSpecialist(BaseSpecialist):
    """
    Tier 1 Local AI Vision Model Specialist.
    Uses local Hugging Face ViT model with pinned commit hash to classify spatial semantics.
    """
    def __init__(self):
        super().__init__(
            name="Spatial Vision Classifier (ViT)",
            specialist_type="SPATIAL_VISION",
            category="AI_MODEL"
        )

    def analyze(self, image_path: str) -> Dict[str, Any]:
        t0 = time.time()
        res = _hf_detector.predict(image_path)
        latency_ms = round((time.time() - t0) * 1000, 1)

        model_status = res.get("model_status", "ANALYSIS UNAVAILABLE")
        ai_indicator = res.get("ai_manipulation_indicator")
        confidence = res.get("model_confidence") or 0.0

        if model_status == "AVAILABLE" and ai_indicator is not None:
            if ai_indicator >= 0.65:
                verdict = "MANIPULATED"
            elif ai_indicator <= 0.35:
                verdict = "AUTHENTIC"
            else:
                verdict = "INCONCLUSIVE"
        elif model_status == "ANALYSIS INCONCLUSIVE":
            verdict = "INCONCLUSIVE"
        else:
            verdict = "UNAVAILABLE"

        return {
            "name": self.name,
            "specialist_type": self.specialist_type,
            "category": self.category,
            "status": "COMPLETED" if model_status == "AVAILABLE" else model_status,
            "verdict": verdict,
            "indicator": round(ai_indicator, 3) if ai_indicator is not None else None,
            "confidence": round(confidence, 3),
            "latency_ms": latency_ms,
            "focus": "Global facial & spatial scene semantics",
            "model_name": res.get("ai_model_name"),
            "model_version": res.get("ai_model_version"),
            "device": res.get("runtime_device", "cpu"),
            "details": f"ViT prediction: {verdict} (Indicator: {ai_indicator if ai_indicator is not None else 'N/A'})"
        }

class FrequencyDomainSpecialist(BaseSpecialist):
    """
    Tier 1 Physical Frequency-Domain Specialist.
    Computes 2D Fast Fourier Transform (FFT) high-frequency power distribution and periodic grid peaks.
    """
    def __init__(self):
        super().__init__(
            name="Frequency-Domain Specialist (2D FFT)",
            specialist_type="FREQUENCY_DOMAIN",
            category="PHYSICAL_SIGNAL"
        )

    def analyze(self, img: Image.Image, fft_anomaly_score: float, checkerboard_score: float) -> Dict[str, Any]:
        t0 = time.time()
        combined_freq_score = round(max(0.0, min(100.0, (fft_anomaly_score * 0.6) + (checkerboard_score * 0.4))), 1)
        latency_ms = round((time.time() - t0) * 1000, 1)

        if combined_freq_score >= 60.0 or checkerboard_score >= 65.0:
            verdict = "MANIPULATED"
            details = f"Periodic frequency lattice artifacts detected ({combined_freq_score}/100 anomaly)."
        elif combined_freq_score <= 35.0:
            verdict = "AUTHENTIC"
            details = "Natural radial frequency attenuation observed."
        else:
            verdict = "INCONCLUSIVE"
            details = f"Moderate frequency distribution anomaly ({combined_freq_score}/100)."

        return {
            "name": self.name,
            "specialist_type": self.specialist_type,
            "category": self.category,
            "status": "COMPLETED",
            "verdict": verdict,
            "indicator": round(combined_freq_score / 100.0, 3),
            "confidence": 0.88,
            "latency_ms": latency_ms,
            "focus": "Periodic frequency spikes & spectral grid artifacts",
            "score": combined_freq_score,
            "details": details
        }

class SyntheticNoiseSpecialist(BaseSpecialist):
    """
    Tier 1 Physical Sensor Noise & PRNU Residual Specialist.
    Measures high-pass Laplacian noise residual variance and channel noise consistency.
    """
    def __init__(self):
        super().__init__(
            name="Synthetic Texture & Noise Specialist",
            specialist_type="SYNTHETIC_TEXTURE",
            category="PHYSICAL_SIGNAL"
        )

    def analyze(self, img: Image.Image, noise_anomaly_score: float) -> Dict[str, Any]:
        t0 = time.time()
        score = round(max(0.0, min(100.0, noise_anomaly_score)), 1)
        latency_ms = round((time.time() - t0) * 1000, 1)

        if score >= 55.0:
            verdict = "MANIPULATED"
            details = f"Synthetic texture smoothing / high-pass noise discrepancy detected ({score}/100)."
        elif score <= 35.0:
            verdict = "AUTHENTIC"
            details = "Continuous optical sensor noise pattern preserved across frame."
        else:
            verdict = "INCONCLUSIVE"
            details = f"Ambiguous sensor noise variance ({score}/100)."

        return {
            "name": self.name,
            "specialist_type": self.specialist_type,
            "category": self.category,
            "status": "COMPLETED",
            "verdict": verdict,
            "indicator": round(score / 100.0, 3),
            "confidence": 0.85,
            "latency_ms": latency_ms,
            "focus": "PRNU sensor noise & generative denoising smoothing",
            "score": score,
            "details": details
        }

class LocalizedPatchSpecialist(BaseSpecialist):
    """
    Tier 1 Local Manipulation & Spatial Patch Specialist.
    Uses PatchLocalizer to detect localized inpainting, splicing, or added objects (e.g. Sunglasses / Face).
    """
    def __init__(self):
        super().__init__(
            name="Localized Region & Inpainting Specialist",
            specialist_type="LOCAL_PATCH",
            category="PHYSICAL_SIGNAL"
        )

    def analyze(self, patch_results: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.time()
        max_patch_anomaly = patch_results.get("max_patch_anomaly", 0.0)
        regions = patch_results.get("localized_regions", [])
        latency_ms = round((time.time() - t0) * 1000, 1)

        if len(regions) > 0 and max_patch_anomaly >= 50.0:
            verdict = "MANIPULATED"
            top_roi = regions[0]
            details = f"Localized anomaly detected in {top_roi.get('semantic_label', 'ROI')} (Score: {top_roi.get('anomaly_score', 0):.1f}%)."
        elif max_patch_anomaly <= 35.0:
            verdict = "AUTHENTIC"
            details = "Uniform spatial patch consistency across entire frame."
        else:
            verdict = "INCONCLUSIVE"
            details = f"Minor patch variance ({max_patch_anomaly:.1f}%), no bounded ROI formed."

        return {
            "name": self.name,
            "specialist_type": self.specialist_type,
            "category": self.category,
            "status": "COMPLETED",
            "verdict": verdict,
            "indicator": round(max_patch_anomaly / 100.0, 3),
            "confidence": 0.90 if len(regions) > 0 else 0.82,
            "latency_ms": latency_ms,
            "focus": "Localized ROIs, inpainting & object insertion (e.g. sunglasses)",
            "score": round(max_patch_anomaly, 1),
            "regions_count": len(regions),
            "details": details
        }

class ProvenanceMetadataSpecialist(BaseSpecialist):
    """
    Tier 3 Provenance & Container Metadata Specialist.
    Inspects C2PA manifests, EXIF camera capture hardware tags, and editing software markers.
    """
    def __init__(self):
        super().__init__(
            name="Metadata & Provenance Specialist",
            specialist_type="PROVENANCE_METADATA",
            category="PROVENANCE"
        )

    def analyze(self, provenance_res: Dict[str, Any], metadata_res: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.time()
        p_status = provenance_res.get("status", "NOT_AVAILABLE")
        p_details = provenance_res.get("details", "")
        meta_score = metadata_res.get("metadata_anomaly_score", 0.0)
        has_editing_suite = metadata_res.get("editing_software_detected", False)
        latency_ms = round((time.time() - t0) * 1000, 1)

        if p_status == "VERIFIED":
            verdict = "AUTHENTIC"
            details = f"C2PA cryptographic provenance verified: {p_details}"
        elif p_status == "INVALID" or has_editing_suite or meta_score >= 50.0:
            verdict = "MANIPULATED"
            details = f"Post-processing editing software tag detected: {metadata_res.get('software', 'Photo Editor')}"
        elif metadata_res.get("has_exif", False) and metadata_res.get("camera_make"):
            verdict = "AUTHENTIC"
            details = f"Authentic camera EXIF tags recorded ({metadata_res.get('camera_make')} {metadata_res.get('camera_model', '')})."
        else:
            verdict = "INCONCLUSIVE"
            details = "No camera hardware metadata or C2PA manifest present."

        return {
            "name": self.name,
            "specialist_type": self.specialist_type,
            "category": self.category,
            "status": "COMPLETED",
            "verdict": verdict,
            "provenance_status": p_status,
            "confidence": 0.95 if p_status == "VERIFIED" else 0.75,
            "latency_ms": latency_ms,
            "focus": "Camera hardware EXIF & C2PA Content Credentials",
            "details": details
        }

class ExternalDetectorAdapter(BaseSpecialist):
    """
    Tier 2 External Independent AI Detector Adapter (e.g. Copyleaks / Hive / Sensity).
    Honest contract: If API key is not configured, clearly reports NOT_CONFIGURED without fabricating fake data.
    """
    def __init__(self):
        super().__init__(
            name="External Independent Detector (Copyleaks Adapter)",
            specialist_type="EXTERNAL_DETECTOR",
            category="EXTERNAL_API"
        )

    def analyze(self, image_path: str) -> Dict[str, Any]:
        t0 = time.time()
        api_key = settings.COPYLEAKS_API_KEY
        if not api_key:
            return {
                "name": self.name,
                "specialist_type": self.specialist_type,
                "category": self.category,
                "status": "NOT_CONFIGURED",
                "verdict": "SKIPPED",
                "indicator": None,
                "confidence": 0.0,
                "latency_ms": 0.0,
                "focus": "Independent cloud AI verification & RLE mask",
                "details": "External Copyleaks API key not set; independent cloud verification skipped."
            }

        try:
            # When API key is provided, execute external request
            url = f"{settings.COPYLEAKS_API_BASE_URL}/ai-image/detect"
            headers = {"Authorization": f"Bearer {api_key}"}
            with open(image_path, "rb") as f:
                files = {"file": f}
                resp = requests.post(url, headers=headers, files=files, timeout=8.0)

            latency_ms = round((time.time() - t0) * 1000, 1)
            if resp.status_code == 200:
                data = resp.json()
                is_ai = data.get("isAiDetected", False)
                ai_prob = data.get("aiProbability", 1.0 if is_ai else 0.0)
                verdict = "MANIPULATED" if is_ai else "AUTHENTIC"
                return {
                    "name": self.name,
                    "specialist_type": self.specialist_type,
                    "category": self.category,
                    "status": "COMPLETED",
                    "verdict": verdict,
                    "indicator": round(ai_prob, 3),
                    "confidence": 0.92,
                    "latency_ms": latency_ms,
                    "focus": "Independent cloud AI verification & RLE mask",
                    "details": f"External detector: {verdict} (AI Probability: {ai_prob * 100:.1f}%)"
                }
            else:
                return {
                    "name": self.name,
                    "specialist_type": self.specialist_type,
                    "category": self.category,
                    "status": "API_ERROR",
                    "verdict": "INCONCLUSIVE",
                    "indicator": None,
                    "confidence": 0.0,
                    "latency_ms": latency_ms,
                    "focus": "Independent cloud AI verification",
                    "details": f"External API returned HTTP {resp.status_code}."
                }
        except Exception as e:
            latency_ms = round((time.time() - t0) * 1000, 1)
            logger.warning(f"External detector adapter execution failed: {e}")
            return {
                "name": self.name,
                "specialist_type": self.specialist_type,
                "category": self.category,
                "status": "NETWORK_UNAVAILABLE",
                "verdict": "SKIPPED",
                "indicator": None,
                "confidence": 0.0,
                "latency_ms": latency_ms,
                "focus": "Independent cloud AI verification",
                "details": f"External service unavailable ({str(e)[:40]}). Local ensemble preserved."
            }

class EnsembleAgreementEngine:
    """
    Aggregates multi-specialist verdicts, calculates consensus agreement ratio,
    and detects forensic signal conflicts between independent specialists.
    """
    @staticmethod
    def evaluate_consensus(specialists: List[Dict[str, Any]]) -> Dict[str, Any]:
        active_specialists = [s for s in specialists if s.get("status") == "COMPLETED" and s.get("verdict") != "SKIPPED"]
        total_active = len(active_specialists)

        manipulated_count = sum(1 for s in active_specialists if s.get("verdict") == "MANIPULATED")
        authentic_count = sum(1 for s in active_specialists if s.get("verdict") == "AUTHENTIC")
        inconclusive_count = sum(1 for s in active_specialists if s.get("verdict") == "INCONCLUSIVE")

        # Consensus Ratio
        decisive_count = manipulated_count + authentic_count
        if decisive_count > 0:
            manipulated_ratio = manipulated_count / decisive_count
            authentic_ratio = authentic_count / decisive_count
        else:
            manipulated_ratio = 0.0
            authentic_ratio = 0.0

        # Conflict Detection:
        # e.g., AI model says MANIPULATED with high confidence, but sensor noise and metadata both say AUTHENTIC
        has_conflict = False
        conflict_details = []

        spatial_s = next((s for s in active_specialists if s.get("specialist_type") == "SPATIAL_VISION"), None)
        noise_s = next((s for s in active_specialists if s.get("specialist_type") == "SYNTHETIC_TEXTURE"), None)
        meta_s = next((s for s in active_specialists if s.get("specialist_type") == "PROVENANCE_METADATA"), None)
        patch_s = next((s for s in active_specialists if s.get("specialist_type") == "LOCAL_PATCH"), None)

        if spatial_s and spatial_s.get("verdict") == "MANIPULATED" and (spatial_s.get("indicator") or 0) >= 0.75:
            if noise_s and noise_s.get("verdict") == "AUTHENTIC" and meta_s and meta_s.get("verdict") == "AUTHENTIC" and (not patch_s or patch_s.get("verdict") == "AUTHENTIC"):
                has_conflict = True
                conflict_details.append("Vision model flagged synthetic textures, but PRNU sensor noise and camera EXIF indicate authentic photographic capture.")

        if spatial_s and spatial_s.get("verdict") == "AUTHENTIC" and (spatial_s.get("indicator") or 1) <= 0.20:
            if patch_s and patch_s.get("verdict") == "MANIPULATED":
                # Localized edit (e.g. sunglasses) on authentic background - this is a localized manipulation rather than conflict!
                pass
            elif noise_s and noise_s.get("verdict") == "MANIPULATED":
                has_conflict = True
                conflict_details.append("Global vision model classified frame as authentic, but physical high-frequency noise shows significant splice disparity.")

        # Overall Consensus Verdict
        if has_conflict:
            consensus_verdict = "CONFLICTING_SIGNALS"
            consensus_label = "⚠️ Conflicting Forensic Signals"
        elif manipulated_count >= 3 or (manipulated_count >= 2 and total_active <= 3) or (manipulated_ratio >= 0.70 and manipulated_count >= 2):
            consensus_verdict = "STRONG_MANIPULATION_CONSENSUS"
            consensus_label = f"🔴 Strong Consensus ({manipulated_count}/{total_active} Signals Indicate Manipulation)"
        elif manipulated_count >= 1 and patch_s and patch_s.get("verdict") == "MANIPULATED":
            consensus_verdict = "LOCALIZED_MANIPULATION_CONSENSUS"
            consensus_label = f"✨ Localized Manipulation Consensus ({manipulated_count}/{total_active} Signals)"
        elif authentic_count >= 3 or (authentic_count >= 2 and total_active <= 3) or (authentic_ratio >= 0.70 and authentic_count >= 2):
            consensus_verdict = "AUTHENTIC_BASELINE_CONSENSUS"
            consensus_label = f"🟢 Authentic Baseline Consensus ({authentic_count}/{total_active} Signals Clean)"
        else:
            consensus_verdict = "INCONCLUSIVE_CONSENSUS"
            consensus_label = f"❓ Inconclusive Consensus ({manipulated_count} Manipulated, {authentic_count} Authentic)"

        return {
            "total_specialists_evaluated": len(specialists),
            "active_specialists_count": total_active,
            "manipulated_signals_count": manipulated_count,
            "authentic_signals_count": authentic_count,
            "inconclusive_signals_count": inconclusive_count,
            "agreement_percentage": round(max(manipulated_ratio, authentic_ratio) * 100, 1) if decisive_count > 0 else 50.0,
            "consensus_verdict": consensus_verdict,
            "consensus_label": consensus_label,
            "has_signal_conflict": has_conflict,
            "conflict_description": " • ".join(conflict_details) if conflict_details else None,
            "specialist_breakdown": specialists
        }
