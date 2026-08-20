"""
Reproducibility Record Builder
Every forensic analysis stores a reproducibility record so results can be re-traced later.
"""
from datetime import datetime
from typing import Dict, Any, Optional
from app.config import settings


class ReproducibilityEngine:
    """
    Builds a structured reproducibility record for each forensic analysis.
    Stored alongside the forensic result so the analysis can be re-traced months later.
    """

    @staticmethod
    def build_record(
        evidence_id: str,
        input_sha256: str,
        modality: str,
        analysis_mode: str,
        model_name: Optional[str],
        model_version: Optional[str],
        forensic_anomaly_score: float,
        ensemble_specialist_count: int
    ) -> Dict[str, Any]:
        return {
            "evidence_id": evidence_id,
            "truthlens_version": settings.VERSION,
            "platform": settings.PROJECT_NAME,
            "analysis_mode": analysis_mode,
            "modality": modality,
            "input_sha256": input_sha256,
            "analysis_timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "ai_model_name": model_name or "Truth Lens Signal Engine",
            "ai_model_version": model_version or "1.0",
            "ai_model_checkpoint": "dima806/deepfake_vs_real_image_detection" if modality == "IMAGE" else "N/A",
            "specialist_ensemble_count": ensemble_specialist_count,
            "heuristic_pipeline": [
                "ELA-95-recompression-variance",
                "2D-FFT-frequency-spectral-peaks",
                "PRNU-high-pass-noise-residual",
                "Sobel-gradient-boundary-analysis",
                "Patch-sliding-ROI-decomposition"
            ],
            "forensic_anomaly_score_recorded": round(forensic_anomaly_score, 2),
            "parameters": {
                "ela_quality": 95,
                "ela_amplification_factor": 10,
                "fft_high_freq_threshold": 0.7,
                "prnu_sigma": 3.0,
                "patch_size_px": 64,
                "patch_stride_px": 32,
                "patch_anomaly_threshold": 0.6
            },
            "disclaimer": (
                "This record enables analysis reproducibility. Re-running on the same SHA-256 input "
                "with the same TruthLens version and model checkpoint should yield equivalent findings. "
                "Local ML model predictions may vary slightly across hardware/runtime environments."
            )
        }
