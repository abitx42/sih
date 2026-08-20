# Truth Lens — Forensic Media Alteration Benchmark Framework

This directory defines the structured dataset specification and evaluation protocol for evaluating Truth Lens across distinct digital alteration modalities.

## 1. Ethical & Scientific Integrity Principle
Forensic systems must avoid advertising blanket accuracy numbers (e.g. "99.8% accurate") derived from synthetic or homogenous datasets. Detection performance fluctuates dramatically under operational conditions (JPEG compression, social media resizing, modern diffusion inpainting, unaligned crops).

Truth Lens only reports performance metrics when evaluated against grounded benchmark runs with documented datasets.

## 2. Standardized Evaluation Modalities

| Modality Category | Ground Truth | Core Challenge | Key Evaluation Metric |
|---|---|---|---|
| `pristine` | Unmodified capture | False-alarm suppression on high-frequency natural scenes | False Positive Rate (FPR) |
| `manual_edit` | Traditional edit/splice | Detecting edge discontinuities, ELA & noise inconsistencies | Bounding Box Recall & Precision |
| `ai_inpaint` | Localized AI replacement | Detecting subtle generative texture artifacts in localized regions | Localization IoU & Regional Reliability |
| `fully_generated` | 100% Synthetic AI | Global frequency anomalies & semantic artifact detection | Generative Indicator AUROC |
| `recompressed` | Multi-generation lossy | Disentangling compression artifacts from genuine forgeries | Inconclusive Transition Rate |

## 3. Benchmark Data Directory Format
When running local evaluation scripts, organize ground truth samples as follows:
```
benchmarks/datasets/
├── pristine/
│   ├── sample_001.jpg
│   └── sample_001_meta.json
├── manual_edit/
│   ├── sample_002.jpg
│   ├── sample_002_mask.png   # Binary ground truth alteration mask
│   └── sample_002_ref.jpg    # Optional pre-edit original reference
├── ai_inpaint/
│   ├── sample_003.jpg
│   └── sample_003_mask.png   # Binary ground truth alteration mask
├── fully_generated/
│   └── sample_004.jpg
└── recompressed/
    └── sample_005.jpg
```
