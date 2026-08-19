# Truth Lens : Final Demo Rehearsal & Presentation Dossier

**Platform:** Truth Lens — Digital Evidence Forensics Platform  
**Target Event:** SIH PS-27 (KAVACH 2023) Jury Presentation  
**Verification Date:** August 20, 2026  
**Status:** ✅ **ALL REHEARSAL CHECKS PASSED (100% PRODUCTION READY)**  

---

## 📋 1. Rehearsal Checklist & Test Results

| Category | Verification Item | Status | Observations / Verification Detail |
|---|---|---|---|
| **Setup & Startup** | Clean Environment Setup | ✅ PASS | Documented in `README.md` & `DEPLOYMENT.md`; zero paid external dependencies. |
| | Secret Safety | ✅ PASS | No secrets or API keys in frontend code; optional `LLM_API_KEY` read safely via server environment. |
| | Uvicorn Server Startup | ✅ PASS | Starts cleanly on `http://127.0.0.1:8000` with static UI mounted at root (`/`). |
| | HF Model Script | ✅ PASS | `scripts/download_model.py` runs with repo-relative import resolution; models cached in `storage/models`. |
| | Demo Seed Script | ✅ PASS | `scripts/seed_demo_data.py` populates all 5 modalities (Image, Video, Audio, Document, Archive) with explicit `[DEMO FIXTURE]` tags. |
| **Forensic Pipeline** | Ingestion & Async 202 | ✅ PASS | Upload returns `202 Accepted` immediately; UI polls status until `COMPLETED`. |
| | Modality Coverage | ✅ PASS | Verified Image (authentic & spliced), Audio (WAV), Video (MP4), Document (PDF), and Archive (ZIP). |
| | Cryptographic Baseline | ✅ PASS | SHA-256, SHA-512, MD5 computed during intake and logged as genesis custody event. |
| | Forensic Risk Engine | ✅ PASS | Multi-signal deterministic risk scoring (`LOW RISK`, `REVIEW REQUIRED`, `HIGH RISK`) with component weighting. |
| | Chain of Custody | ✅ PASS | Append-only application custody log records intake, analysis, integrity verification, and report exports. |
| | PDF Report Generation | ✅ PASS | Generates `truth_lens_report_{evidence_id}.pdf` with forensic disclaimers and structured findings table. |
| | AI Copilot & CoE Fallback | ✅ PASS | Seamlessly falls back to `Local Deterministic Engine` when network or API key is absent without user-facing errors. |
| **Presentation Quality**| Branding Consistency | ✅ PASS | 100% rebranded to **Truth Lens** (`See the signals. Review the evidence.`); 0 user-facing `EVIDENCE-X` occurrences. |
| | Responsive Layout | ✅ PASS | Tested on desktop (1440px), tablet (992px), and mobile (375px/600px). |
| | Honest Disclaimers | ✅ PASS | Explicit disclaimers on UI, PDF, and API responses emphasizing indicators are review aids, not judicial proof. |
| **Automated Tests** | Non-Slow Test Suite | ✅ PASS | `pytest -v -m "not slow"`: **49 passed, 3 deselected, 0 failures**. |

---

## ⚡ 2. Fastest 5-Minute Presentation Sequence for Judges

Follow this exact sequence for a high-impact, smooth demonstration:

```
[0:00 - 0:45] 1. Problem & Architecture Positioning (Dashboard View)
              • Open Dashboard (http://localhost:8000).
              • Point to Tagline: "See the signals. Review the evidence."
              • Emphasize the core thesis: We do NOT provide black-box binary "real/fake" guesses. 
                Truth Lens decouples cryptographic bitstream preservation (SHA-256) from physical heuristics, 
                local Vision Transformer classification, and tamper-evident custody documentation.

[0:45 - 1:45] 2. Evidence Intake & Cryptographic Baseline (Upload View)
              • Switch to "Evidence Intake".
              • Select Case: CASE-2026-001 (Operation CyberShield).
              • Drag and drop an image or audio file.
              • Show immediate 202 Accepted ingestion -> instant SHA-256/SHA-512/MD5 fingerprint calculation.
              • Show the live BackgroundTasks status spinner transitioning from ANALYZING to COMPLETED.

[1:45 - 2:45] 3. Multi-Signal Forensic Lab (Deep-Dive View)
              • Switch to "Forensic Lab" and select the newly ingested exhibit.
              • Review the 3-Tier Risk Score badge (e.g., LOW RISK vs HIGH RISK).
              • Point to physical signal tabs:
                - Error Level Analysis (ELA 95%) showing compression delta.
                - 2D Fast Fourier Transform (FFT) showing spectral peak anomalies.
                - Sensor-Noise Consistency heuristic.
                - Sampled real decoded video keyframes or audio STFT spectrogram.
              • Highlight the Technical Findings breakdown table.

[2:45 - 3:45] 4. Forensic Copilot & Grounded Q&A
              • Click "⚡ Generate AI Explanation" on the right panel.
              • Show structured 4-part synthesis (Summary, Technical Findings Requiring Review, Limitations, Next Steps).
              • Type a question in the Copilot Chat box: "Why was this exhibit flagged with ELA variance?"
              • Show instant grounded answer with offline fallback guarantee.

[3:45 - 4:30] 5. Application Custody Log & PDF Export
              • Click "⛓️ Custody Log" to display the append-only SQLite custody stream with timestamps and actor signatures.
              • Click "Export Custody Log (JSON)" to download the forensic audit payload.
              • Click "📥 Export PDF Report" -> Open the downloaded `truth_lens_report_{evidence_id}.pdf`.
              • Show the official header, case metadata, risk classification, technical findings table, and court-ready disclaimer.

[4:30 - 5:00] 6. Q&A & Wrap-Up
              • Summarize compliance with SIH PS-27 / KAVACH 2023 requirements.
              • Open floor for jury questions.
```

---

## 🛠️ 3. Exact Commands Used During Rehearsal

### Server Startup
```bash
# 1. Activate Python virtual environment
source venv/bin/activate

# 2. Run database initialization & seed demo exhibits
python scripts/seed_demo_data.py

# 3. Start production server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Full Test Suite Execution
```bash
PYTHONPATH=. pytest -v -m "not slow"
```

### Automated Rehearsal Verification
```bash
python scripts/verify_demo_rehearsal.py
```

---

## 🛡️ 4. Fallback Plans for Demo Scenarios

| Scenario / Failure Mode | Automatic Fallback Mechanism | Manual Mitigation for Presenter |
|---|---|---|
| **No Internet Connection at Venue** | Local PyTorch model runs completely offline from `storage/models`. CoE Gateway queries gracefully timeout and trigger `Local Deterministic Engine`. | The entire demo runs 100% locally on `localhost:8000`. Present without any internet connection. |
| **Model Download Blocks in Strict Network** | Hugging Face model is already pre-cached in `storage/models`. If absent, pipeline catches download errors, marks `model_status="ANALYSIS_UNAVAILABLE"`, and evaluates physical signals. | Pre-seed exhibits using `python scripts/seed_demo_data.py` before presenting. |
| **Cloudflare Tunnel (`cloudflared`) Unavailable** | Platform is accessible on the local network (LAN) via `http://<YOUR_LAN_IP>:8000` because `--host 0.0.0.0` is bound. | Present directly from the laptop browser or connect jury devices to the same local Wi-Fi / hotspot. |
| **Server Crash or Terminal Interruption** | FastAPI startup recovery automatically sweeps SQLite for any orphaned `ANALYZING` records, marks them `FAILED`, and records an `ANALYSIS_FAILED` custody event. | Simply restart `uvicorn app.main:app --port 8000` — previous evidence and custody records remain intact. |

---

## 🔧 5. Demo-Critical Fixes Implemented During Rehearsal

1. **`scripts/download_model.py` and `scripts/seed_demo_data.py` Imports**:
   - Added automatic project root resolution to `sys.path` so scripts execute properly from any directory or CLI environment.
2. **All 5 Modalities in Demo Seed**:
   - Expanded demo fixtures to include Image (Authentic), Image (Spliced), Audio (WAV), Document (PDF), Archive (ZIP), and Video (MP4), all clearly labeled with `[DEMO FIXTURE - NOT REAL EVIDENCE]`.
3. **Numpy Float32 Serialization in Risk Engine**:
   - Added custom JSON serializer in `routes_evidence.py` to prevent float32 serialization crashes during exhibit storage.
4. **CoE AI Schema Alignment**:
   - Updated `AIExplanationResponse` schema to support multi-line limitations and deterministic offline fallback.
