# EVIDENCE-X : Digital Evidence Forensic Verification Platform
> **Smart India Hackathon (SIH 2026) • PS-27: Deepfake Detection for Digital Evidence Verification (KAVACH 2023)**  
> *Tagline: "Verify Before You Trust."*

---

## 🎯 Executive Summary & Core Mission
Traditional deepfake detectors output a binary `"Real or Fake"` verdict or an isolated probability score. In a legal and digital forensic context, this is insufficient.

EVIDENCE-X addresses the central investigative question:  
> **"Can an investigator trust this digital file as forensic evidence?"**

By combining **Cryptographic Bitstream Integrity (SHA-256)**, **Structural & Container Metadata Forensics**, **C2PA Content Credentials Provenance**, **Multi-Modal AI Manipulation Detection**, **Explainable Signal Deconstruction (ELA, FFT, Vocoder analysis)**, and an **Immutable Chain of Custody Ledger**, EVIDENCE-X provides courts and law enforcement with a defensible, multi-signal verification dossier.

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
            │ Specialized AI Models │  (Ensemble Vision, Audio Vocoder, Temporal Net)
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
│ Natural Narrative / Q&A │   │ High-Integrity PDF Dossier
└─────────────────────────┘   └─────────────────────────┘
```

---

## ⚡ Key Features

1. **Deterministic Multi-Signal Risk Engine**:
   - Scores 0 - 100 with 3-tier categorization:
     - 🟢 **LOW RISK (0 - 30)**: Sound cryptographic baseline, uniform noise, authentic provenance.
     - 🟡 **REVIEW REQUIRED (31 - 70)**: Inconclusive compression anomalies, missing metadata, or moderate synthesis signals requiring human inspection.
     - 🔴 **HIGH RISK (71 - 100)**: Compounding manipulation indicators (e.g., ELA boundary discrepancy + high AI probability + editing software headers).
2. **Zero Mocked Scores**: All hashes, ELA diffs, 2D FFT spectrums, STFT spectrograms, and temporal flickers are computed mathematically on ingested bytes.
3. **Multi-Modal Forensic Coverage**:
   - **Images**: Error Level Analysis (ELA 95%), 2D FFT Frequency Grid artifact detection, PRNU noise residual variance, EXIF camera tags.
   - **Videos**: Container inspection, keyframe sampling, temporal luminosity flicker analysis, inter-frame structural stability.
   - **Audio**: STFT Spectrogram visual exhibits, acoustic splicing detection, neural vocoder high-frequency cutoff analysis.
   - **Documents**: PDF multiple EOF incremental revision checks, embedded JavaScript/launch streams, DOCX/XLSX OOXML macro inspection.
   - **Archives**: Zip Slip path traversal defense, archive bomb protection, and nested file SHA-256 fingerprinting.
4. **C2PA / Content Credentials Provenance**: Automatic verification of cryptographic provenance manifests and post-processing signatures.
5. **Immutable Chain of Custody**: Complete ISO/IEC 27037 compliant audit trail capturing timestamp, actor identity, action taken, and recorded SHA-256 hash.
6. **Forensic Copilot (TCET CoE Gateway / Qwen 3.6)**: Context-isolated assistant for executive narrative drafting, investigator recommendations, and interactive evidence Q&A (with deterministic offline fallback).
7. **Court-Ready PDF Reports**: High-integrity multi-page PDF generation featuring embedded visual exhibits (ELA, FFT, Spectrogram), cryptographic tables, and legal disclaimers.

---

## 🚀 Quickstart & Setup

### 1. Requirements
- Python 3.9+
- SQLite3

### 2. Installation
```bash
# Clone or navigate to directory
cd sih

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Running the Server
```bash
# Start FastAPI server on localhost:8000
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at: **`http://localhost:8000`**

---

## 🧪 Running Automated Tests
```bash
source venv/bin/activate
pytest -v
```
All unit tests for cryptographic integrity, risk engine weighting, security validators, analyzers, and API endpoints run automatically.

---

## ⚖️ Standards & Legal Alignment
- **NIST Guidelines on AI-Assisted Digital Evidence Verification**
- **ISO/IEC 27037**: Guidelines for identification, collection, acquisition, and preservation of digital evidence
- **Section 65B Indian Evidence Act / Bharatiya Sakshya Adhiniyam**: Electronic record certificate format compliance
