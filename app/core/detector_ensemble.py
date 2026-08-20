"""
app/core/detector_ensemble.py
==============================
Multi-Specialist Forensic Analysis Ensemble & Consensus Engine.

Truth Lens uses specialized local heuristic engines and vision classifiers to inspect
media across multiple domains.

CALIBRATION & SCIENTIFIC SAFETY:
  - Heuristic specialists never declare definitive verdicts such as 'AUTHENTIC' or 'MANIPULATED'.
  - Specialists report neutral signal states:
      'ALTERATION_SIGNAL_DETECTED'
      'NO_STRONG_ANOMALY_DETECTED'
      'INCONCLUSIVE'
      'UNAVAILABLE'
      'VERIFIED_PROVENANCE' (strictly after real cryptographic validation)
  - No external cloud detectors are invoked; Truth Lens is 100% local and free.
  - Confidence values are uncalibrated (calibration_status: 'UNVALIDATED').
"""
import time
import logging
from typing import Dict, Any, List, Optional
from PIL import Image

from app.config import settings
from app.analyzers.hf_image_detector import HFImageDetector
from app.analyzers.patch_localizer import PatchLocalizer

logger = logging.getLogger(__name__)

_hf_detector = HFImageDetector()

CALIBRATION_STATUS = "UNVALIDATED"

# Neutral signal states
SIGNAL_ALTERATION_DETECTED    = "ALTERATION_SIGNAL_DETECTED"
SIGNAL_NO_STRONG_ANOMALY      = "NO_STRONG_ANOMALY_DETECTED"
SIGNAL_INCONCLUSIVE           = "INCONCLUSIVE"
SIGNAL_UNAVAILABLE            = "UNAVAILABLE"
SIGNAL_VERIFIED_PROVENANCE    = "VERIFIED_PROVENANCE"


class BaseSpecialist:
    """Base class for all forensic specialists in the Truth Lens ensemble."""
    def __init__(self, name: str, specialist_type: str, category: str):
        self.name = name
        self.specialist_type = specialist_type
        self.category = category


class SpatialVisionSpecialist(BaseSpecialist):
    """
    Local AI Vision Model Specialist.
    Uses local Hugging Face ViT model with pinned commit hash as a probabilistic visual indicator.
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

        if model_status == "AVAILABLE" and ai_indicator is not None:
            if ai_indicator >= 0.65:
                verdict = SIGNAL_ALTERATION_DETECTED
                strength = "HIGH" if ai_indicator >= 0.85 else "MODERATE"
            elif ai_indicator <= 0.35:
                verdict = SIGNAL_NO_STRONG_ANOMALY
                strength = "MODERATE"
            else:
                verdict = SIGNAL_INCONCLUSIVE
                strength = "LOW"
        elif model_status == "ANALYSIS INCONCLUSIVE":
            verdict = SIGNAL_INCONCLUSIVE
            strength = "LOW"
        else:
            verdict = SIGNAL_UNAVAILABLE
            strength = "NONE"

        return {
            "name": self.name,
            "specialist_type": self.specialist_type,
            "category": self.category,
            "status": "COMPLETED" if model_status == "AVAILABLE" else model_status,
            "verdict": verdict,
            "indicator": round(ai_indicator, 3) if ai_indicator is not None else None,
            "evidence_strength": strength,
            "calibration_status": CALIBRATION_STATUS,
            "latency_ms": latency_ms,
            "focus": "Global facial & spatial scene semantics",
            "model_name": res.get("ai_model_name"),
            "model_version": res.get("ai_model_version"),
            "device": res.get("runtime_device", "cpu"),
            "details": f"ViT screening signal: {verdict} (Statistical indicator: {ai_indicator if ai_indicator is not None else 'N/A'})"
        }


class FrequencyDomainSpecialist(BaseSpecialist):
    """
    Physical Frequency-Domain Specialist.
    Computes 2D Fast Fourier Transform (FFT) high-frequency power distribution and periodic grid peaks.
    """
    def __init__(self):
        super().__init__(
            name="Frequency-Domain Specialist (2D FFT)",
            specialist_type="FREQUENCY_DOMAIN",
            category="PHYSICAL_SIGNAL"
        )

    def analyze(self, img: Optional[Image.Image], fft_anomaly_score: float, checkerboard_score: float) -> Dict[str, Any]:
        t0 = time.time()
        combined_freq_score = round(max(0.0, min(100.0, (fft_anomaly_score * 0.6) + (checkerboard_score * 0.4))), 1)
        latency_ms = round((time.time() - t0) * 1000, 1)

        if combined_freq_score >= 60.0 or checkerboard_score >= 65.0:
            verdict = SIGNAL_ALTERATION_DETECTED
            strength = "HIGH" if combined_freq_score >= 80.0 else "MODERATE"
            details = f"Periodic frequency lattice artifacts detected ({combined_freq_score}/100 anomaly)."
        elif combined_freq_score <= 35.0:
            verdict = SIGNAL_NO_STRONG_ANOMALY
            strength = "MODERATE"
            details = "Natural radial frequency attenuation observed."
        else:
            verdict = SIGNAL_INCONCLUSIVE
            strength = "LOW"
            details = f"Moderate frequency distribution anomaly ({combined_freq_score}/100)."

        return {
            "name": self.name,
            "specialist_type": self.specialist_type,
            "category": self.category,
            "status": "COMPLETED",
            "verdict": verdict,
            "indicator": round(combined_freq_score / 100.0, 3),
            "evidence_strength": strength,
            "calibration_status": CALIBRATION_STATUS,
            "latency_ms": latency_ms,
            "focus": "Periodic frequency spikes & spectral grid artifacts",
            "score": combined_freq_score,
            "details": details
        }


class SyntheticNoiseSpecialist(BaseSpecialist):
    """
    Physical Sensor Noise & PRNU Residual Specialist.
    Measures high-pass Laplacian noise residual variance and channel noise consistency.
    """
    def __init__(self):
        super().__init__(
            name="Synthetic Texture & Noise Specialist",
            specialist_type="SYNTHETIC_TEXTURE",
            category="PHYSICAL_SIGNAL"
        )

    def analyze(self, img: Optional[Image.Image], noise_anomaly_score: float) -> Dict[str, Any]:
        t0 = time.time()
        score = round(max(0.0, min(100.0, noise_anomaly_score)), 1)
        latency_ms = round((time.time() - t0) * 1000, 1)

        if score >= 55.0:
            verdict = SIGNAL_ALTERATION_DETECTED
            strength = "HIGH" if score >= 75.0 else "MODERATE"
            details = f"High-pass noise residual discrepancy detected ({score}/100 anomaly)."
        elif score <= 35.0:
            verdict = SIGNAL_NO_STRONG_ANOMALY
            strength = "MODERATE"
            details = "Continuous optical sensor noise pattern consistent across frame."
        else:
            verdict = SIGNAL_INCONCLUSIVE
            strength = "LOW"
            details = f"Ambiguous sensor noise variance ({score}/100)."

        return {
            "name": self.name,
            "specialist_type": self.specialist_type,
            "category": self.category,
            "status": "COMPLETED",
            "verdict": verdict,
            "indicator": round(score / 100.0, 3),
            "evidence_strength": strength,
            "calibration_status": CALIBRATION_STATUS,
            "latency_ms": latency_ms,
            "focus": "PRNU sensor noise & generative denoising smoothing",
            "score": score,
            "details": details
        }


class LocalizedPatchSpecialist(BaseSpecialist):
    """
    Localized Anomaly & Spatial Patch Specialist.
    Uses PatchLocalizer to detect localized statistical anomaly concentrations across spatial grid cells.
    """
    def __init__(self):
        super().__init__(
            name="Localized Region & Patch Specialist",
            specialist_type="LOCAL_PATCH",
            category="PHYSICAL_SIGNAL"
        )

    def analyze(self, patch_results: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.time()
        max_patch_anomaly = patch_results.get("max_patch_anomaly", 0.0)
        regions = patch_results.get("localized_regions", [])
        latency_ms = round((time.time() - t0) * 1000, 1)

        if len(regions) > 0 and max_patch_anomaly >= 50.0:
            verdict = SIGNAL_ALTERATION_DETECTED
            strength = "HIGH" if max_patch_anomaly >= 75.0 else "MODERATE"
            top_roi = regions[0]
            details = f"Statistical anomaly concentrated in {top_roi.get('semantic_label', 'ROI')} (Score: {top_roi.get('anomaly_score', 0):.1f}%)."
        elif max_patch_anomaly <= 35.0:
            verdict = SIGNAL_NO_STRONG_ANOMALY
            strength = "MODERATE"
            details = "Uniform spatial patch consistency across entire frame."
        else:
            verdict = SIGNAL_INCONCLUSIVE
            strength = "LOW"
            details = f"Minor patch variance ({max_patch_anomaly:.1f}%), no bounded ROI formed."

        return {
            "name": self.name,
            "specialist_type": self.specialist_type,
            "category": self.category,
            "status": "COMPLETED",
            "verdict": verdict,
            "indicator": round(max_patch_anomaly / 100.0, 3),
            "evidence_strength": strength,
            "calibration_status": CALIBRATION_STATUS,
            "latency_ms": latency_ms,
            "focus": "Localized anomaly concentrations & spatial patch discontinuities",
            "score": round(max_patch_anomaly, 1),
            "regions_count": len(regions),
            "details": details
        }


class ProvenanceMetadataSpecialist(BaseSpecialist):
    """
    Provenance & Container Metadata Specialist.
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

        if p_status == "CRYPTOGRAPHIC_VALIDATION_PASSED":
            verdict = SIGNAL_VERIFIED_PROVENANCE
            strength = "HIGH"
            details = f"C2PA cryptographic provenance verified: {p_details}"
        elif p_status == "INVALID" or has_editing_suite or meta_score >= 50.0:
            verdict = SIGNAL_ALTERATION_DETECTED
            strength = "MODERATE"
            details = f"Post-processing editing software tag detected: {metadata_res.get('software', 'Photo Editor')}"
        elif metadata_res.get("has_exif", False) and metadata_res.get("camera_make"):
            verdict = SIGNAL_NO_STRONG_ANOMALY
            strength = "LOW"
            details = f"Camera hardware EXIF tags present ({metadata_res.get('camera_make')} {metadata_res.get('camera_model', '')}) - context only, not capture proof."
        else:
            verdict = SIGNAL_INCONCLUSIVE
            strength = "NONE"
            details = "No camera hardware metadata or C2PA manifest present."

        return {
            "name": self.name,
            "specialist_type": self.specialist_type,
            "category": self.category,
            "status": "COMPLETED",
            "verdict": verdict,
            "provenance_status": p_status,
            "evidence_strength": strength,
            "calibration_status": CALIBRATION_STATUS,
            "latency_ms": latency_ms,
            "focus": "Camera hardware EXIF & C2PA Content Credentials",
            "details": details
        }


class EnsembleAgreementEngine:
    """
    Aggregates multi-specialist signal states and calculates consensus ratio.
    """
    @staticmethod
    def evaluate_consensus(specialists: List[Dict[str, Any]]) -> Dict[str, Any]:
        active_specialists = [s for s in specialists if s.get("status") == "COMPLETED" and s.get("verdict") != "SKIPPED"]
        total_active = len(active_specialists)

        alteration_count = sum(1 for s in active_specialists if s.get("verdict") == SIGNAL_ALTERATION_DETECTED)
        baseline_count = sum(1 for s in active_specialists if s.get("verdict") in (SIGNAL_NO_STRONG_ANOMALY, SIGNAL_VERIFIED_PROVENANCE))
        inconclusive_count = sum(1 for s in active_specialists if s.get("verdict") in (SIGNAL_INCONCLUSIVE, SIGNAL_UNAVAILABLE))

        decisive_count = alteration_count + baseline_count
        if decisive_count > 0:
            alteration_ratio = alteration_count / decisive_count
            baseline_ratio = baseline_count / decisive_count
        else:
            alteration_ratio = 0.0
            baseline_ratio = 0.0

        # Conflict Detection:
        has_conflict = False
        conflict_details = []

        spatial_s = next((s for s in active_specialists if s.get("specialist_type") == "SPATIAL_VISION"), None)
        noise_s   = next((s for s in active_specialists if s.get("specialist_type") == "SYNTHETIC_TEXTURE"), None)
        meta_s    = next((s for s in active_specialists if s.get("specialist_type") == "PROVENANCE_METADATA"), None)
        patch_s   = next((s for s in active_specialists if s.get("specialist_type") == "LOCAL_PATCH"), None)

        if spatial_s and spatial_s.get("verdict") == SIGNAL_ALTERATION_DETECTED and (spatial_s.get("indicator") or 0) >= 0.75:
            if noise_s and noise_s.get("verdict") == SIGNAL_NO_STRONG_ANOMALY and meta_s and meta_s.get("verdict") == SIGNAL_NO_STRONG_ANOMALY and (not patch_s or patch_s.get("verdict") == SIGNAL_NO_STRONG_ANOMALY):
                has_conflict = True
                conflict_details.append("Vision model indicated potential synthetic features, but sensor noise consistency and camera EXIF show baseline characteristics.")

        if spatial_s and spatial_s.get("verdict") == SIGNAL_NO_STRONG_ANOMALY and (spatial_s.get("indicator") or 1) <= 0.20:
            if noise_s and noise_s.get("verdict") == SIGNAL_ALTERATION_DETECTED:
                has_conflict = True
                conflict_details.append("Global vision model indicated baseline scene characteristics, but physical noise analysis indicates anomaly disparity.")

        # Overall Consensus Verdict
        if has_conflict:
            consensus_verdict = "CONFLICTING_SIGNALS"
            consensus_label = "⚠️ Conflicting Forensic Signals"
        elif alteration_count >= 3 or (alteration_count >= 2 and total_active <= 3) or (alteration_ratio >= 0.70 and alteration_count >= 2):
            consensus_verdict = "STRONG_ALTERATION_SIGNAL_CONSENSUS"
            consensus_label = f"🔴 Alteration Signal Consensus ({alteration_count}/{total_active} Specialists Flag Anomaly)"
        elif alteration_count >= 1 and patch_s and patch_s.get("verdict") == SIGNAL_ALTERATION_DETECTED:
            consensus_verdict = "LOCALIZED_ANOMALY_CONSENSUS"
            consensus_label = f"✨ Localized Anomaly Consensus ({alteration_count}/{total_active} Signals)"
        elif baseline_count >= 3 or (baseline_count >= 2 and total_active <= 3) or (baseline_ratio >= 0.70 and baseline_count >= 2):
            consensus_verdict = "BASELINE_SIGNAL_CONSENSUS"
            consensus_label = f"🟢 Baseline Signal Consensus ({baseline_count}/{total_active} Specialists Unflagged)"
        else:
            consensus_verdict = "INCONCLUSIVE_CONSENSUS"
            consensus_label = f"❓ Inconclusive Consensus ({alteration_count} Alteration Signals, {baseline_count} Baseline Signals)"

        return {
            "total_specialists_evaluated": len(specialists),
            "active_specialists_count": total_active,
            "alteration_signals_count": alteration_count,
            "baseline_signals_count": baseline_count,
            "inconclusive_signals_count": inconclusive_count,
            # Backwards compatibility fields
            "manipulated_signals_count": alteration_count,
            "authentic_signals_count": baseline_count,
            "agreement_percentage": round(max(alteration_ratio, baseline_ratio) * 100, 1) if decisive_count > 0 else 50.0,
            "consensus_verdict": consensus_verdict,
            "consensus_label": consensus_label,
            "has_signal_conflict": has_conflict,
            "conflict_description": " • ".join(conflict_details) if conflict_details else None,
            "specialist_breakdown": specialists
        }
