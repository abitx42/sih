import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"

EVIDENCE_DIR = STORAGE_DIR / "evidence"
THUMBNAILS_DIR = STORAGE_DIR / "thumbnails"
FORENSIC_DIR = STORAGE_DIR / "forensic"
REPORTS_DIR = STORAGE_DIR / "reports"
AUDIT_DIR = STORAGE_DIR / "audit"
DB_PATH = STORAGE_DIR / "evidence_x.db"

# Ensure directories exist
for directory in [STORAGE_DIR, EVIDENCE_DIR, THUMBNAILS_DIR, FORENSIC_DIR, REPORTS_DIR, AUDIT_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

class Settings:
    PROJECT_NAME: str = "EVIDENCE-X"
    TAGLINE: str = "Digital Evidence Forensic Verification Platform"
    VERSION: str = "1.0.0"
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

    # TCET CoE AI Gateway / LLM Configuration
    LLM_API_BASE_URL: str = os.getenv("LLM_API_BASE_URL", "").strip()
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "").strip()
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen3.6-35b-a3b")
    
    # Scoring Weights for Deterministic Risk Engine
    WEIGHT_INTEGRITY: float = 0.25
    WEIGHT_AI_MANIPULATION: float = 0.30
    WEIGHT_FORENSIC_SIGNALS: float = 0.25
    WEIGHT_METADATA_ANOMALIES: float = 0.10
    WEIGHT_PROVENANCE: float = 0.10

settings = Settings()
