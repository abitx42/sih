import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from PIL import Image

from app.config import settings, MODEL_CACHE_DIR

logger = logging.getLogger(__name__)

class HFImageDetector:
    """
    Dedicated Local Hugging Face ML Vision Classifier.
    Runs 'dima806/deepfake_vs_real_image_detection' strictly in local memory.
    Never sends evidence images to external servers.
    If the model fails to load or inference fails, returns ANALYSIS UNAVAILABLE.
    """

    def __init__(self):
        self.model_name = settings.HF_MODEL_NAME
        self.model_revision = settings.HF_MODEL_REVISION
        self.local_files_only = settings.HF_LOCAL_FILES_ONLY
        self.cache_dir = str(MODEL_CACHE_DIR)
        self._processor = None
        self._model = None
        self._device = None
        self._id2label = None
        self._is_loaded = False
        self._load_error = None

    def _get_device(self):
        try:
            import torch
            if torch.cuda.is_available():
                return torch.device("cuda")
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return torch.device("mps")
            return torch.device("cpu")
        except Exception:
            return "cpu"

    def load_model(self) -> bool:
        """
        Lazily loads the PyTorch ViT model and AutoImageProcessor.
        Attempts local cache first, then configured setting.
        Returns True if loaded, False otherwise.
        """
        if self._is_loaded and self._model is not None:
            return True

        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForImageClassification

            self._device = self._get_device()
            
            # Try local cache first to avoid network timeout delays
            try:
                self._processor = AutoImageProcessor.from_pretrained(
                    self.model_name,
                    revision=self.model_revision,
                    cache_dir=self.cache_dir,
                    local_files_only=True
                )
                self._model = AutoModelForImageClassification.from_pretrained(
                    self.model_name,
                    revision=self.model_revision,
                    cache_dir=self.cache_dir,
                    local_files_only=True
                )
            except Exception:
                if self.local_files_only:
                    raise
                # Fallback to standard loading if allowed
                self._processor = AutoImageProcessor.from_pretrained(
                    self.model_name,
                    revision=self.model_revision,
                    cache_dir=self.cache_dir,
                    local_files_only=False
                )
                self._model = AutoModelForImageClassification.from_pretrained(
                    self.model_name,
                    revision=self.model_revision,
                    cache_dir=self.cache_dir,
                    local_files_only=False
                )

            self._model.to(self._device)
            self._model.eval()

            # Inspect label mapping defensively
            self._id2label = getattr(self._model.config, "id2label", {0: "REAL", 1: "FAKE"})
            self._is_loaded = True
            self._load_error = None
            logger.info(f"Successfully loaded HF Model '{self.model_name}'. id2label: {self._id2label}")
            return True
        except Exception as e:
            self._is_loaded = False
            self._load_error = str(e)
            logger.warning(f"Unable to load local HF model '{self.model_name}': {e}")
            return False

    def _classify_label_defensively(self, raw_label: str) -> str:
        """
        Normalizes classification labels defensively.
        Matches common synthetic vs real synonyms without blind assumptions.
        """
        clean = str(raw_label).strip().lower()
        if any(term in clean for term in ["fake", "manipulated", "synthetic", "generated", "deepfake", "ai_generated", "label_1", "1"]):
            return "MANIPULATED"
        if any(term in clean for term in ["real", "authentic", "pristine", "original", "natural", "label_0", "0"]):
            return "UNMANIPULATED"
        return "UNKNOWN"

    def predict(self, image_input: Any) -> Dict[str, Any]:
        """
        Executes local inference on an image file path or PIL Image object.
        Returns complete reproducible model output schema.
        """
        timestamp = datetime.utcnow().isoformat() + "Z"
        device_str = str(self._device) if self._device else "unknown"

        # 1. Check if model can be loaded
        if not self.load_model():
            return {
                "ai_model_name": self.model_name,
                "ai_model_version": self.model_revision,
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": "ANALYSIS UNAVAILABLE",
                "label_mapping": self._id2label,
                "predicted_label": None,
                "runtime_device": device_str,
                "inference_timestamp": timestamp,
                "error_detail": f"Local ML inference unavailable: {self._load_error}"
            }

        # 2. Load & Validate Image
        try:
            if isinstance(image_input, (str, Path)):
                img = Image.open(image_input).convert("RGB")
            elif isinstance(image_input, Image.Image):
                img = image_input.convert("RGB")
            else:
                raise ValueError("Invalid image input type.")
        except Exception as e:
            return {
                "ai_model_name": self.model_name,
                "ai_model_version": self.model_revision,
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": "ERROR",
                "label_mapping": self._id2label,
                "predicted_label": None,
                "runtime_device": device_str,
                "inference_timestamp": timestamp,
                "error_detail": f"Malformed or unreadable image stream: {e}"
            }

        # 3. Local PyTorch Inference
        try:
            import torch
            inputs = self._processor(images=img, return_tensors="pt")
            inputs = {k: v.to(self._device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=-1).squeeze(0)

            # Defensive label resolution from id2label
            manipulated_prob = None
            unmanipulated_prob = None

            for class_idx, prob_val in enumerate(probs.tolist()):
                raw_lbl = self._id2label.get(class_idx, str(class_idx))
                normalized_lbl = self._classify_label_defensively(raw_lbl)
                if normalized_lbl == "MANIPULATED":
                    manipulated_prob = prob_val
                elif normalized_lbl == "UNMANIPULATED":
                    unmanipulated_prob = prob_val

            # If mapping not recognized, fallback to top prediction
            top_idx = int(torch.argmax(probs).item())
            top_prob = float(probs[top_idx].item())
            top_raw_label = self._id2label.get(top_idx, str(top_idx))
            top_normalized = self._classify_label_defensively(top_raw_label)

            if manipulated_prob is not None:
                ai_indicator = round(float(manipulated_prob), 4)
            else:
                ai_indicator = round(top_prob if top_normalized == "MANIPULATED" else (1.0 - top_prob), 4)

            return {
                "ai_model_name": self.model_name,
                "ai_model_version": self.model_revision,
                "ai_manipulation_indicator": ai_indicator,
                "model_confidence": round(top_prob, 4),
                "model_status": "AVAILABLE",
                "label_mapping": self._id2label,
                "predicted_label": top_normalized,
                "raw_label": top_raw_label,
                "runtime_device": device_str,
                "inference_timestamp": timestamp,
                "error_detail": None
            }
        except Exception as e:
            logger.error(f"Inference error in local HF detector: {e}")
            return {
                "ai_model_name": self.model_name,
                "ai_model_version": self.model_revision,
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": "ANALYSIS UNAVAILABLE",
                "label_mapping": self._id2label,
                "predicted_label": None,
                "runtime_device": device_str,
                "inference_timestamp": timestamp,
                "error_detail": f"Local inference execution failed: {e}"
            }
