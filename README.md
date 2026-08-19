# EVIDENCE-X : Digital Evidence Forensic Verification Platform
> **Smart India Hackathon (SIH 2026) • PS-27: Deepfake Detection for Digital Evidence Verification (KAVACH 2023)**  
> *Tagline: "Verify Before You Trust."*

---

## 🎯 Executive Summary & Core Mission
Traditional deepfake detectors output a binary `"Real or Fake"` verdict or an isolated probability score. In a legal and digital forensic context, this is insufficient.

EVIDENCE-X addresses the central investigative question:  
> **"Can an investigator trust this digital file as forensic evidence?"**

By combining **Cryptographic Bitstream Integrity (SHA-256)**, **Structural & Container Metadata Forensics**, **C2PA Content Credentials Provenance**, **Local Vision Transformer Classification (dima806/deepfake_vs_real_image_detection)**, **Explainable Physical Signal Deconstruction (ELA 95%, 2D FFT, PRNU Noise, STFT Spectrogram, Waveform Envelope)**, an **Immutable Chain of Custody Ledger**, and an **AI Forensic Copilot (TCET CoE Gateway / Qwen 3.6)**, EVIDENCE-X provides courts and law enforcement with a defensible, multi-signal verification dossier.

---

## 🏛️ System Architecture

```
DIGITAL EVIDENCE FILE (Image, Video, Audio, Document, Archive)
                        │
                        ▼
            ┌───────────────────────┐
            │   Security & Intake   │  (Magic Bytes, Path Sanitization, Zip Slip Defense)
            └───────────┬───────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │ Cryptographic Baseline│  (SHA-256, SHA-512, MD5, Genesis Custody Event)
            └───────────┬───────────┘
                        │
      ┌─────────────────┼─────────────────┐
      ▼                 ▼                 ▼
 ┌──────────┐     ┌───────────┐     ┌───────────┐
 │ Metadata │     │Provenance │     │ Modality  │
 │ & EXIF   │     │  (C2PA)   │     │ Analyzers │
 └────┬─────┘     └─────┬─────┘     └─────┬─────┘
      │                 │                 │
      │   ┌─────────────┴─────────────┐   │
      │   │ Image: ELA, FFT, PRNU     │   │
      │   │ Video: OpenCV Real Frames │   │
      │   │ Audio: Waveform, STFT     │   │
      │   │ Docs:  Incremental Update │   │
      │   └─────────────┬─────────────┘   │
      │                 │                 │
      └─────────────────┼─────────────────┘
                        ▼
            ┌───────────────────────┐
            │ Local ML Classifier   │  (dima806/deepfake_vs_real_image_detection)
            └───────────┬───────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │  Explainability Engine│  (Structured Findings: Severity, Location, Cause)
            └───────────┬───────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │   Deterministic Risk  │  (0-100 Score -> LOW / REVIEW REQ / HIGH RISK)
            └───────────┬───────────┘
                        │
      ┌─────────────────┴─────────────────┐
      ▼                                   ▼
┌─────────────────────────┐   ┌─────────────────────────┐
│ Forensic Copilot (Qwen) │   │ Court-Ready ReportLab   │
│ TCET CoE Gateway / Q&A  │   │ High-Integrity PDF Dossier
└─────────────────────────┘   └─────────────────────────┘
```

---

## ⚡ Key Features & Reliability Principles

1. **Independent Heuristic & ML Signal Separation**:
   - **Forensic Anomaly Score (0-100)**: Derived from physical compression artifacts (ELA 95%), 2D FFT periodic frequency spikes, PRNU sensor noise inconsistency, and container modification records.
   - **Local ML Vision Model**: `dima806/deepfake_vs_real_image_detection` running in-process via PyTorch.
   - **Honest Failure Handling**: If the model is offline or uninstalled, the system outputs `model_status: "ANALYSIS UNAVAILABLE"`. If class labels cannot be mapped, it returns `model_status: "ANALYSIS INCONCLUSIVE"`. **Zero made-up or hallucinated scores.**

2. **Real Video Forensics & Frame Aggregation**:
   - **True Frame Decoding**: Decodes real video streams using OpenCV (`opencv-python-headless`), sampling up to 16 uniformly distributed keyframes across the file duration.
   - **Statistical Aggregation**: Reuses the local ViT classifier on real decoded frames and aggregates results using the **median** indicator and interquartile range (IQR) dispersion.
   - **Threshold Safety**: Requires a minimum of 3 valid decoded frames with model predictions; otherwise returns `ANALYSIS INCONCLUSIVE` or `ANALYSIS UNAVAILABLE` with null AI indicator.
   - **Supported Codecs**: Native support for MP4 (H.264/AVC, MPEG-4), AVI, MOV, WebM.

3. **Scientifically Honest Audio Forensics**:
   - **True Audio Decoding**: Native Python decoding for uncompressed PCM WAV (8/16/24/32-bit), with optional local FFmpeg fallback for compressed formats (MP3, M4A, OGG, FLAC).
   - **Physical Acoustic Metrics**: Computes RMS energy variation, silence intervals, clipping ratio, spectral centroid, 85% spectral roll-off, high-frequency energy ratio (>4kHz), and STFT spectral flux step deltas (splice candidates).
   - **Visual Artifacts**: Generates high-contrast waveform envelope (`waveform_*.png`) and STFT spectrogram (`spectrogram_*.png`) under `storage/forensic/`.
   - **No Fictional Audio ML**: No fabricated vocoder neural networks or synthetic voice probabilities; outputs `model_status: "ANALYSIS UNAVAILABLE"` and `ai_manipulation_indicator: None`.
   - **Audio Disclaimer**: *"Audio forensic signals are automated screening indicators, not proof of synthetic speech, editing, authenticity, or legal admissibility."*

4. **TCET CoE AI Gateway & Forensic Copilot**:
   - **Model**: `qwen3.6` hosted via OpenAI-compatible endpoint at `https://ai.tcetcercd.in/v1`.
   - **Purpose**: Optional forensic interpretation service providing 4-part structured synthesis:
     1. Investigator Summary
     2. Technical Findings Requiring Review
     3. Physical Limitations
     4. Recommended Next Steps
   - **Prompt Injection Defense**: Untrusted evidence inputs (filenames, user notes, findings) are safely encapsulated in `<untrusted_evidence_data>` boundaries.
   - **Zero-Failure Fallback**: If the gateway times out (15s timeout), returns 401/502, or if `LLM_API_KEY` is not set, the platform automatically utilizes its built-in deterministic forensic engine. Ingestion and analysis never fail.
   - **Endpoint**: `POST /api/evidence/{evidence_id}/explain`.
   - **Mandatory Notice**: *"AI-assisted interpretation only. This does not determine authenticity, manipulation, or legal admissibility."*

5. **Deterministic Multi-Signal Risk Engine**:
   - Scores 0 - 100 with 3-tier categorization:
     - 🟢 **LOW RISK (0 - 30)**: Sound cryptographic baseline, uniform noise, authentic provenance.
     - 🟡 **REVIEW REQUIRED (31 - 70)**: Inconclusive compression anomalies, unavailable ML analysis, or moderate synthesis signals requiring human inspection.
     - 🔴 **HIGH RISK (71 - 100)**: Compounding manipulation indicators.
   - **Integrity Rule**: SHA-256 integrity is recorded strictly as file bitstream preservation; it does **not** artificially reduce AI manipulation risk or prove authenticity.

6. **C2PA / Content Credentials Provenance**: Automatic verification of cryptographic provenance manifests and post-processing signatures.

7. **Immutable Chain of Custody**: Complete ISO/IEC 27037 compliant audit trail capturing timestamp, actor identity, action taken, and recorded SHA-256 hash.

8. **Court-Ready PDF Reports**: High-integrity multi-page PDF generation featuring embedded visual exhibits (ELA, FFT, Waveform, Spectrogram), model reproducibility metadata (revision commit, runtime device, label mapping), and legal disclaimers.

---

## 🔒 Security & Environment Setup

> [!CAUTION]
> **CRITICAL SECURITY DIRECTIVE: NEVER PASTE OR COMMIT API KEYS.**
> Read all credentials exclusively from local environment variables (`.env`). Never hardcode or commit keys to Git repositories.

### Configuration (`.env`)
Create a `.env` file in the root directory (already included in `.gitignore`):

```env
# Server Settings
PORT=8000
HOST=0.0.0.0
DEBUG=True

# Local Storage Directory
STORAGE_DIR=./storage

# Hugging Face Vision Model Config (Local In-Memory Inference)
HF_MODEL_NAME=dima806/deepfake_vs_real_image_detection
HF_MODEL_REVISION=29e4cf9efc543845610045f6ba7e88e5cf9d9301
HF_LOCAL_FILES_ONLY=False

# TCET CoE AI Gateway Configuration (Optional Forensic Copilot)
# Leave blank to use built-in offline deterministic NLG engine
LLM_API_BASE_URL=https://ai.tcetcercd.in/v1
LLM_API_KEY=
LLM_MODEL=qwen3.6

# Security Constraints
MAX_UPLOAD_SIZE_MB=150
ALLOWED_EXTENSIONS=jpg,jpeg,png,webp,mp4,avi,mov,mkv,wav,mp3,pdf,docx,xlsx,pptx,zip,tar,gz
```

---

## 🚀 Quickstart

### 1. Installation
```bash
# Clone or navigate to repository
cd sih

# Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install pinned dependencies
pip install -r requirements.txt
```

### 2. Running the Server
```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at: **`http://localhost:8000`**

---

## 🧪 Testing & CI Workflow

### Local Test Execution
Run the full non-slow test suite (41 unit & integration tests):
```bash
source venv/bin/activate
PYTHONPATH=. pytest -v -m "not slow"
```

To run all tests including slow integration tests:
```bash
PYTHONPATH=. pytest -v
```

### GitHub Actions CI Workflow (`.github/workflows/tests.yml`)
Automated continuous integration runs on every `push` and `pull_request` to branch `main`:
- Sets up Python 3.9 on `ubuntu-latest`
- Installs pinned dependencies from `requirements.txt`
- Executes `PYTHONPATH=. pytest -v -m "not slow" --junitxml=pytest-report.xml`
- Uploads `pytest-failure-report` artifact if any tests fail.

---

## ⚖️ Standards & Legal Alignment
- **NIST Guidelines on AI-Assisted Digital Evidence Verification**
- **ISO/IEC 27037**: Guidelines for identification, collection, acquisition, and preservation of digital evidence
- **Section 65B Indian Evidence Act / Bharatiya Sakshya Adhiniyam**: Electronic record certificate format compliance
