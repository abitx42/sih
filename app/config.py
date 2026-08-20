import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Read local .env if present without external dependencies
env_file = BASE_DIR / ".env"
if env_file.exists():
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

STORAGE_DIR = BASE_DIR / "storage"
EVIDENCE_DIR = STORAGE_DIR / "evidence"
THUMBNAILS_DIR = STORAGE_DIR / "thumbnails"
FORENSIC_DIR = STORAGE_DIR / "forensic"
REPORTS_DIR = STORAGE_DIR / "reports"
AUDIT_DIR = STORAGE_DIR / "audit"
MODEL_CACHE_DIR = STORAGE_DIR / "models"
DB_PATH = STORAGE_DIR / "evidence_x.db"

# Ensure directories exist
for directory in [STORAGE_DIR, EVIDENCE_DIR, THUMBNAILS_DIR, FORENSIC_DIR, REPORTS_DIR, AUDIT_DIR, MODEL_CACHE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

class Settings:
    PROJECT_NAME: str = "Truth Lens"
    TAGLINE: str = "Digital Evidence Forensics Platform"
    SHORT_TAGLINE: str = "See the signals. Review the evidence."
    VERSION: str = "1.2.0"
    PS_NUMBER: str = "SIH PS-27 (KAVACH 2023)"
    
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    
    # Security
    MAX_UPLOAD_SIZE_BYTES: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "150")) * 1024 * 1024
    ALLOWED_EXTENSIONS: set = {
        "jpg", "jpeg", "png", "webp", "bmp", "tiff",
        "mp4", "avi", "mov", "mkv", "webm",
        "wav", "mp3", "ogg", "flac", "m4a",
        "pdf", "docx", "xlsx", "pptx", "txt",
        "zip", "tar", "gz", "7z"
    }
    ALLOWED_ORIGINS: list = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:3000").split(",")
        if origin.strip()
    ]

    # Hugging Face Vision Model Config (Reproducibility & Local Inference)
    # Pinned to specific model commit hash for full auditability
    HF_MODEL_NAME: str = os.getenv("HF_MODEL_NAME", "dima806/deepfake_vs_real_image_detection")
    HF_MODEL_REVISION: str = os.getenv("HF_MODEL_REVISION", "29e4cf9efc543845610045f6ba7e88e5cf9d9301")
    HF_LOCAL_FILES_ONLY: bool = os.getenv("HF_LOCAL_FILES_ONLY", "False").lower() == "true"

    # TCET CoE AI Gateway Configuration (Forensic Copilot Text Explanation Engine Only)
    # Note: Only structured text prompt findings are processed for natural language summary. No image bytes are ever transmitted.
    LLM_API_BASE_URL: str = os.getenv("LLM_API_BASE_URL", "https://ai.tcetcercd.in/v1").strip().rstrip("/")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "").strip()
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen3.6")

    # 3-Tier Analysis Modes
    ANALYSIS_MODE_QUICK: str = "QUICK_SCAN"
    ANALYSIS_MODE_FULL: str = "FULL_ANALYSIS"
    ANALYSIS_MODE_ADVANCED: str = "ADVANCED_INVESTIGATION"
    
    # Scoring Weights for Deterministic Risk Engine
    WEIGHT_AI_MANIPULATION: float = 0.40
    WEIGHT_FORENSIC_SIGNALS: float = 0.40
    WEIGHT_METADATA_ANOMALIES: float = 0.10
    WEIGHT_PROVENANCE: float = 0.10

    # ── Localization Policy Thresholds ──────────────────────────────────────
    # Minimum distinct signal categories (e.g. Pixel Forensics, Frequency/Noise, Metadata)
    # required to issue LOCALIZED_ANOMALY_REQUIRING_REVIEW.
    LOCALIZATION_MIN_SUPPORTING_CATEGORIES: int = int(os.getenv("LOCALIZATION_MIN_SUPPORTING_CATEGORIES", "2"))

    # Minimum SSIM score (0–1) after alignment for reference comparison to be considered
    # aligned enough to produce a meaningful difference map.
    REFERENCE_COMPARISON_ALIGNMENT_THRESHOLD: float = float(os.getenv("REFERENCE_COMPARISON_ALIGNMENT_THRESHOLD", "0.60"))

    # Maximum reference image upload size in bytes
    REFERENCE_MAX_SIZE_BYTES: int = int(os.getenv("REFERENCE_MAX_SIZE_MB", "50")) * 1024 * 1024

    # Global AI model score threshold above which GENERATIVE-IMAGE INDICATOR is asserted.
    GENERATIVE_INDICATOR_THRESHOLD: float = float(os.getenv("GENERATIVE_INDICATOR_THRESHOLD", "0.75"))

settings = Settings()

