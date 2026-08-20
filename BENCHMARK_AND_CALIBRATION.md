# Truth Lens — Benchmark & Confidence Calibration Protocol

This document defines the scientific methodology, empirical metrics, and calibration requirements necessary before reporting quantitative confidence or accuracy percentages in Truth Lens.

---

## 1. Core Principle: Zero Uncalibrated Certainty Claims

Truth Lens operates under a strict forensic honesty principle:
- **No synthetic percentages**: Automated heuristic screening scores are **NOT** calibrated probability distributions.
- **Unvalidated status**: All heuristic localization scores, agreement maps, and multi-specialist grids are visibly designated as `CALIBRATION: UNVALIDATED`.
- **Pre-calibration constraint**: No UI card, API schema, or PDF report may display `"98% confidence"` or claim that an exhibit is `"authentically certified"` or `"definitively manipulated"` based on heuristic algorithms.

---

## 2. Required Empirical Benchmark Measurements

To transition any analyzer from `CALIBRATION: UNVALIDATED` to a calibrated state, the analyzer must be evaluated across the five standardized ground-truth benchmark modalities defined in `benchmarks/benchmark_structure.json`:

### A. False Positive Rate (FPR) on Pristine Media
- **Dataset**: Minimum 1,000 uncompressed / camera-original images across diverse ISO settings, sensors, and lighting conditions.
- **Measurement**: Proportion of clean captures where heuristic anomaly scores or vision models trigger false alarms (`ALTERATION_SIGNAL_DETECTED` or `LOCALIZED_ANOMALY_REQUIRING_REVIEW`).
- **Target**: FPR $< 5.0\%$ at the operational threshold.

### B. True Detection Rate (Sensitivity / Recall) on Edits
- **Dataset**: Minimum 1,000 spliced, inpainted, retouched, and object-inserted media with corresponding binary ground-truth masks.
- **Measurement**: True positive rate across varying editing magnitudes ($< 2\%$ of image area to $> 25\%$).

### C. Localization Overlap (Intersection-over-Union / IoU)
- **Measurement**: Jaccard index between the predicted `localized_anomaly_heatmap` and ground-truth binary edit mask $M_{\text{gt}}$:
  $$\text{IoU} = \frac{|M_{\text{pred}} \cap M_{\text{gt}}|}{|M_{\text{pred}} \cup M_{\text{gt}}|}$$
- **Threshold**: Mean IoU (mIoU) and bounding box recall at $\text{IoU} \ge 0.50$.

### D. Robustness Under Transcoding & Lossy Recompression
- **Dataset**: Pristine and manipulated exhibits passed through 1 to 5 generations of JPEG compression (Quality 95, 85, 75, 60), WebP transcoding, and downscaling.
- **Measurement**: Anomaly score decay curve, transition rate into `INCONCLUSIVE`, and false-alarm explosion threshold.

---

## 3. Machine-Readable Results Schema (Template)

Benchmark results must be stored in `benchmarks/results/{benchmark_run_id}.json` using this exact schema. No values may be populated without a documented dataset evaluation run:

```json
{
  "benchmark_run_id": "RUN-2026-EXAMPLE",
  "evaluation_date_utc": null,
  "truthlens_version": "1.0.0",
  "dataset_metadata": {
    "dataset_name": "DocumentedGroundTruthDataset",
    "dataset_version": "1.0",
    "dataset_sha256": null,
    "total_samples": 0
  },
  "modality_results": {
    "pristine": {
      "sample_count": 0,
      "false_positive_rate": null,
      "inconclusive_rate": null
    },
    "manual_edit": {
      "sample_count": 0,
      "true_positive_rate": null,
      "localization_miou": null
    },
    "ai_inpaint": {
      "sample_count": 0,
      "true_positive_rate": null,
      "localization_miou": null
    },
    "fully_generated": {
      "sample_count": 0,
      "generative_auroc": null,
      "true_positive_rate": null
    },
    "recompressed": {
      "sample_count": 0,
      "inconclusive_rate": null,
      "stability_index": null
    }
  },
  "calibration_certified": false,
  "notes": "Template schema. No accuracy or confidence percentages claimed prior to executed benchmark evaluation."
}
```

---

## 4. Current State & Immediate Architecture Limitation

- **Current Analyzer**: `TruthLens-LocalELA-v1` (CPU multi-signal heuristic engine).
- **Current Calibration Status**: `UNVALIDATED`.
- **Remaining Limitation**: Truth Lens still requires a trained, benchmarked segmentation model (such as TruFor or CAT-Net running on GPU hardware) for calibrated, high-IoU localized edit detection.
