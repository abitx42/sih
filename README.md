# EVIDENCE-X : Digital Evidence Forensic Verification Platform
> **Smart India Hackathon (SIH 2026) • PS-27: Deepfake Detection for Digital Evidence Verification (KAVACH 2023)**  
> *Tagline: "Verify Before You Trust."*

---

## 🎯 Executive Summary & Core Mission
Traditional deepfake detectors output a binary `"Real or Fake"` verdict or an isolated probability score. In a legal and digital forensic context, this is insufficient.

EVIDENCE-X addresses the central investigative question:  
> **"Can an investigator trust this digital file as forensic evidence?"**

By combining **Cryptographic Bitstream Integrity (SHA-256)**, **Structural & Container Metadata Forensics**, **C2PA Content Credentials Provenance**, **Local Vision Transformer Classification (dima806/deepfake_vs_real_image_detection)**, **Explainable Heuristic Signal Deconstruction (ELA 95%, 2D FFT, PRNU Noise)**, and an **Immutable Chain of Custody Ledger**, EVIDENCE-X provides courts and law enforcement with a defensible, multi-signal verification dossier.

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
      │   │ Video: Flicker, Keyframes │   │
      │   │ Audio: Spectrogram, Voice │   │
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
   - **Forensic Anomaly Score (0-100)**: Derived from physical compression artifacts (ELA 95%), 2D FFT periodic frequency spikes, PRNU sensor noise inconsistency, and EXIF modification records.
   - **Local ML Vision Model**: `dima806/deepfake_vs_real_image_detection` running in-process via PyTorch.
   - **Honest Failure Handling**: If the model is offline or uninstalled, the system outputs `model_status: "ANALYSIS UNAVAILABLE"`. If class labels cannot be mapped, it returns `model_status: "ANALYSIS INCONCLUSIVE"`. **Zero made-up or hallucinated scores.**

2. **Deterministic Multi-Signal Risk Engine**:
   - Scores 0 - 100 with 3-tier categorization:
     - 🟢 **LOW RISK (0 - 30)**: Sound cryptographic baseline, uniform noise, authentic provenance.
     - 🟡 **REVIEW REQUIRED (31 - 70)**: Inconclusive compression anomalies, unavailable ML analysis, or moderate synthesis signals requiring human inspection.
     - 🔴 **HIGH RISK (71 - 100)**: Compounding manipulation indicators (e.g., ELA boundary discrepancy + high AI indicator + editing software headers).
   - **Integrity Rule**: SHA-256 integrity is recorded strictly as file bitstream preservation; it does **not** artificially reduce AI manipulation risk or prove authenticity.

3. **C2PA / Content Credentials Provenance**: Automatic verification of cryptographic provenance manifests and post-processing signatures.

4. **Immutable Chain of Custody**: Complete ISO/IEC 27037 compliant audit trail capturing timestamp, actor identity, action taken, and recorded SHA-256 hash.

5. **Forensic Copilot (TCET CoE AI Gateway)**:
   - Configured for `https://ai.tcetcercd.in/v1` with model `qwen3.6`.
   - Context-isolated assistant for executive narrative drafting, investigator recommendations, and interactive evidence Q&A (with deterministic offline fallback).

6. **Court-Ready PDF Reports**: High-integrity multi-page PDF generation featuring embedded visual exhibits (ELA, FFT, Spectrogram), model reproducibility metadata (revision commit, runtime device, label mapping), and legal disclaimers.

---

## 🚀 Quickstart & Setup

### 1. Requirements
- Python 3.9+
- SQLite3

### 2. Installation
```bash
# Clone or navigate to directory
cd sih

# Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install pinned dependencies
pip install -r requirements.txt

# (Optional) Pre-download & cache local Hugging Face vision model
PYTHONPATH=. python3 scripts/download_model.py
```

### 3. Running the Server
```bash
# Start FastAPI server on localhost:8000
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at: **`http://localhost:8000`**

---

## 🧪 Testing & CI Workflow

### Local Test Execution
Run the full test suite excluding slow tests:
```bash
source venv/bin/activate
PYTHONPATH=. pytest -v -m "not slow"
```

To run all tests including slow real-model integration tests:
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
