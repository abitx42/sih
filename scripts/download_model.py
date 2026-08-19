import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from transformers import AutoImageProcessor, AutoModelForImageClassification
from app.config import settings, MODEL_CACHE_DIR

def cache_hf_model():
    print(f"Downloading & caching model '{settings.HF_MODEL_NAME}' to '{MODEL_CACHE_DIR}'...")
    try:
        AutoImageProcessor.from_pretrained(
            settings.HF_MODEL_NAME,
            revision=settings.HF_MODEL_REVISION,
            cache_dir=str(MODEL_CACHE_DIR)
        )
        AutoModelForImageClassification.from_pretrained(
            settings.HF_MODEL_NAME,
            revision=settings.HF_MODEL_REVISION,
            cache_dir=str(MODEL_CACHE_DIR)
        )
        print("Model downloaded and cached locally successfully!")
    except Exception as e:
        print(f"Model download error: {e}")

if __name__ == "__main__":
    cache_hf_model()
