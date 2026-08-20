# Truth Lens Deployment & Demo Guide

**Problem Statement:** SIH PS-27 (KAVACH 2023) — Digital Evidence Verification Platform  
**Target Environment:** Localhost / LAN / Cloudflare Tunnel Prototype  

---

## 1. Architectural Overview & Demo Topology

Truth Lens is a full-stack digital forensics platform consisting of:
- **Backend:** FastAPI (Python 3.9+) with asynchronous ingestion pipeline (`BackgroundTasks`).
- **Database & Storage:** SQLite (`storage/evidence_x.db`) with localized exhibit storage (`storage/evidence/`, `storage/forensic/`).
- **Machine Learning Engine:** Local PyTorch Hugging Face Vision Transformer (`dima806/deepfake_vs_real_image_detection` @ revision `29e4cf9efc543845610045f6ba7e88e5cf9d9301`).
- **Explainability Copilot:** TCET CoE AI Gateway (`qwen3.6`) with strict prompt injection containment and deterministic offline fallback.
- **Frontend:** Responsive forensic console served directly from `app/static/`.

> [!IMPORTANT]
> **Why Vercel / Netlify Are Not Suitable for the Complete Application:**  
> Serverless platforms like Vercel have strict payload limits (4.5 MB), 10–15s execution timeouts, ephemeral filesystems (no persistent SQLite or exhibit blobs), and no GPU/PyTorch runtime support. Vercel can only host static frontends. Truth Lens requires a persistent Python environment for multi-frame video decoding, signal FFT/ELA computation, and local ML inference.

---

## 2. One-Command Cloudflare Demo Launcher (macOS)

For live demonstrations, hackathon presentations, and jury evaluations, launch the complete Truth Lens application and obtain an encrypted public HTTPS URL with one command:

```bash
./scripts/start_demo.sh
```

### What it does:
1. Validates the local Python virtual environment (`venv/bin/python`) and `cloudflared` CLI installation.
2. Verifies port `8000` availability (explaining how to resolve conflicts if occupied).
3. Boots Truth Lens locally on `127.0.0.1:8000` in production mode.
4. Polls `http://127.0.0.1:8000/health` until HTTP 200 is confirmed.
5. Initializes an encrypted Cloudflare Quick Tunnel (`cloudflared tunnel --url http://127.0.0.1:8000`).
6. Prints the generated `https://*.trycloudflare.com` URL for mobile/laptop jury evaluation.
7. Safely terminates both the tunnel and backend server upon pressing `Ctrl+C`.

To cleanly stop demo processes at any time from another terminal:
```bash
./scripts/stop_demo.sh
```

> [!WARNING]
> - **Ephemeral URL:** The `https://*.trycloudflare.com` link is temporary and generated anew each time the script is started.
> - **Connection Keep-Alive:** The host laptop, active internet connection, and terminal process must remain running while sharing the link.
> - **Public Demo Notice:** This demo interface has no user authentication and must not be used to process real, sensitive, or confidential evidence.
> - **Zero Key Exposure:** The script never reads, modifies, or prints `.env` or API credentials.

---


## 3. Environment Setup & Configuration

### Step 1: Clone Repository & Set Up Virtual Environment
```bash
git clone https://github.com/abitx42/sih.git
cd sih
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables (`.env`)
Create a local `.env` file in the project root:

```env
# Server
HOST=0.0.0.0
PORT=8000
DEBUG=False

# Allowed CORS Origins (Comma-separated)
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000

# TCET CoE AI Gateway (Optional LLM Explanation Service)
LLM_API_BASE_URL=https://ai.tcetcercd.in/v1
LLM_API_KEY=
LLM_MODEL=qwen3.6

# Local Hugging Face Vision Transformer
HF_MODEL_NAME=dima806/deepfake_vs_real_image_detection
HF_MODEL_REVISION=29e4cf9efc543845610045f6ba7e88e5cf9d9301
HF_LOCAL_FILES_ONLY=False
MAX_UPLOAD_SIZE_MB=150
```

> [!CAUTION]
> **Security Directive:** Never commit `.env` or paste API keys into source files. The application automatically falls back to deterministic local rule-based forensic explanations if `LLM_API_KEY` is empty.

---

## 4. Pre-Warming the Local Hugging Face Model

To avoid internet download delays during the live demo, pre-warm and cache the Vision Transformer weights in advance:

```bash
# Run one inference smoke test to download model weights to storage/models/
venv/bin/python3 -c "
from app.analyzers.hf_image_detector import HFImageDetector
from PIL import Image
detector = HFImageDetector()
dummy_img = Image.new('RGB', (224, 224), color=(128, 128, 128))
res = detector.predict(dummy_img)
print('Model pre-warm complete:', res)
"
```

---

## 5. Starting the Application

### Option A: Local & LAN Presentation (Standard)
```bash
# Activate virtualenv and start server
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open [http://localhost:8000](http://localhost:8000) in your browser.

### Option B: Cloudflare Tunnel for Live Public HTTPS Access
In a separate terminal:
```bash
cloudflared tunnel --url http://localhost:8000
```
`cloudflared` will generate a public URL (e.g. `https://random-words.trycloudflare.com`). Share this URL with judges for real-time mobile/laptop evaluation.

---

## 6. Live Presentation Smoke-Test Checklist

Before presenting to evaluators, verify the following 6-point checklist:

- [ ] **Health Check:** Open `http://localhost:8000/api/health` and verify `{"status": "HEALTHY"}`.
- [ ] **Case Investigation Workspace:** Open `http://localhost:8000` -> Navigate to **Cases** -> Open a case workspace to review live KPIs, risk breakdown, and custody timeline.
- [ ] **Bulk Ingestion:** Select 2-3 files in **Evidence Intake** and verify the batch queue polls each exhibit concurrently until `COMPLETED`.
- [ ] **Client-Side Filtering:** In the Case Workspace, test search by filename, modality filters, and risk sorting.
- [ ] **Case Summary PDF Export:** Click **📄 Export Case Summary (PDF)** and verify the generated case dossier PDF.
- [ ] **Image & Physical Signals:** Ingest a sample image and verify ELA heatmap, 2D FFT spectrum, and ViT indicator in the Lab view.
- [ ] **Cryptographic Baseline Re-Verification:** Click **🛡️ Re-Verify Hash** in the Lab view and confirm `PRESERVED (BASELINE MATCH)`.
- [ ] **Individual PDF Report:** Click **📄 Export Forensic Report (PDF)** for an individual exhibit.
- [ ] **AI Explanation Copilot:** Click **⚡ Generate AI Explanation** to demonstrate grounded LLM synthesis.

---

## 7. Prototype Limitations & Operational Boundaries

1. **No User Authentication / RBAC**: Open demo endpoints without JWT authentication or multi-tenant permission controls.
2. **In-Process Concurrency & SQLite**: Runs via in-memory `BackgroundTasks` and local SQLite; not designed for high-concurrency enterprise workloads.
3. **Container-Level Provenance Only**: Scans for C2PA container markers; does not perform full cryptographic X.509 certificate chain validation.
4. **Indicators, Not Proof**: Vision transformer and heuristic scores are screening indicators, not legal determinations or judicial proof.
5. **Mandatory Human Corroboration**: All exported PDF reports and findings require qualified forensic examiner review before evidentiary submission.
