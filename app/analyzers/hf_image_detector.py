import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image

from app.config import settings, MODEL_CACHE_DIR

logger = logging.getLogger(__name__)

class SingleModelRunner:
    """Helper class to load and execute inference for a single local HF vision classifier."""

    def __init__(self, model_name: str, model_revision: str = "", role: str = "GENERATIVE_AI"):
        self.model_name = model_name
        self.model_revision = model_revision or None
        self.role = role
        self.cache_dir = str(MODEL_CACHE_DIR)
        self.local_files_only = settings.HF_LOCAL_FILES_ONLY
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
        if self._is_loaded and self._model is not None:
            return True

        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForImageClassification

            self._device = self._get_device()

            load_kwargs = {"cache_dir": self.cache_dir}
            if self.model_revision:
                load_kwargs["revision"] = self.model_revision

            # Try local cache first to avoid network timeout delays
            try:
                self._processor = AutoImageProcessor.from_pretrained(
                    self.model_name,
                    local_files_only=True,
                    **load_kwargs
                )
                self._model = AutoModelForImageClassification.from_pretrained(
                    self.model_name,
                    local_files_only=True,
                    **load_kwargs
                )
            except Exception:
                if self.local_files_only:
                    raise
                # Fallback to standard loading if allowed
                self._processor = AutoImageProcessor.from_pretrained(
                    self.model_name,
                    local_files_only=False,
                    **load_kwargs
                )
                self._model = AutoModelForImageClassification.from_pretrained(
                    self.model_name,
                    local_files_only=False,
                    **load_kwargs
                )

            self._model.to(self._device)
            self._model.eval()

            self._id2label = getattr(self._model.config, "id2label", {0: "REAL", 1: "FAKE"})
            self._is_loaded = True
            self._load_error = None
            logger.info(f"Loaded HF Model '{self.model_name}' ({self.role}). id2label: {self._id2label}")
            return True
        except Exception as e:
            self._is_loaded = False
            self._load_error = str(e)
            logger.warning(f"Unable to load local HF model '{self.model_name}': {e}")
            return False

    def _classify_label_defensively(self, raw_label: str) -> str:
        """
        Normalizes classification labels defensively across model architectures.
        Matches common synthetic vs real synonyms (including 'artificial' and 'human').
        """
        clean = str(raw_label).strip().lower()
        if any(term in clean for term in ["artificial", "fake", "manipulated", "synthetic", "generated", "deepfake", "ai_generated", "ai"]):
            return "MANIPULATED"
        if any(term in clean for term in ["human", "real", "authentic", "pristine", "original", "natural"]):
            return "UNMANIPULATED"
        return "UNKNOWN"

    def predict(self, img: Image.Image) -> Dict[str, Any]:
        timestamp = datetime.utcnow().isoformat() + "Z"
        device_str = str(self._device) if self._device else "unknown"

        if not self.load_model():
            return {
                "ai_model_name": self.model_name,
                "ai_model_version": self.model_revision or "latest",
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": "ANALYSIS UNAVAILABLE",
                "label_mapping": self._id2label,
                "predicted_label": None,
                "runtime_device": device_str,
                "inference_timestamp": timestamp,
                "role": self.role,
                "error_detail": f"Local ML inference unavailable: {self._load_error}"
            }

        try:
            import torch
            inputs = self._processor(images=img, return_tensors="pt")
            inputs = {k: v.to(self._device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=-1).squeeze(0)

            manipulated_prob = None
            unmanipulated_prob = None
            has_recognized_mapping = False

            for class_idx, prob_val in enumerate(probs.tolist()):
                raw_lbl = self._id2label.get(class_idx, str(class_idx))
                normalized_lbl = self._classify_label_defensively(raw_lbl)
                if normalized_lbl == "MANIPULATED":
                    manipulated_prob = prob_val
                    has_recognized_mapping = True
                elif normalized_lbl == "UNMANIPULATED":
                    unmanipulated_prob = prob_val
                    has_recognized_mapping = True

            top_idx = int(torch.argmax(probs).item())
            top_prob = float(probs[top_idx].item())
            top_raw_label = self._id2label.get(top_idx, str(top_idx))

            if not has_recognized_mapping:
                return {
                    "ai_model_name": self.model_name,
                    "ai_model_version": self.model_revision or "latest",
                    "ai_manipulation_indicator": None,
                    "model_confidence": round(top_prob, 4),
                    "model_status": "ANALYSIS INCONCLUSIVE",
                    "label_mapping": self._id2label,
                    "predicted_label": "UNKNOWN",
                    "raw_label": top_raw_label,
                    "runtime_device": device_str,
                    "inference_timestamp": timestamp,
                    "role": self.role,
                    "error_detail": "Model class labels could not be safely mapped to manipulation categories."
                }

            if manipulated_prob is not None:
                ai_indicator = round(float(manipulated_prob), 4)
                predicted_lbl = "MANIPULATED" if ai_indicator >= 0.5 else "UNMANIPULATED"
            elif unmanipulated_prob is not None:
                ai_indicator = round(1.0 - float(unmanipulated_prob), 4)
                predicted_lbl = "MANIPULATED" if ai_indicator >= 0.5 else "UNMANIPULATED"
            else:
                ai_indicator = None
                predicted_lbl = "UNKNOWN"

            return {
                "ai_model_name": self.model_name,
                "ai_model_version": self.model_revision or "latest",
                "ai_manipulation_indicator": ai_indicator,
                "model_confidence": round(top_prob, 4),
                "model_status": "AVAILABLE",
                "label_mapping": self._id2label,
                "predicted_label": predicted_lbl,
                "raw_label": top_raw_label,
                "runtime_device": device_str,
                "inference_timestamp": timestamp,
                "role": self.role,
                "error_detail": None
            }
        except Exception as e:
            logger.error(f"Inference error in model '{self.model_name}': {e}")
            return {
                "ai_model_name": self.model_name,
                "ai_model_version": self.model_revision or "latest",
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": "ANALYSIS UNAVAILABLE",
                "label_mapping": self._id2label,
                "predicted_label": None,
                "runtime_device": device_str,
                "inference_timestamp": timestamp,
                "role": self.role,
                "error_detail": f"Inference execution failed: {e}"
            }


class HFImageDetector:
    """
    Dedicated Multi-Model Neural Vision Forensic Ensemble (v3.0 — Triple Engine).
    Coordinates local execution of three complementary specialized neural vision architectures:

      1. Generative Diffusion & AI Scene Specialist ('umm-maybe/AI-image-detector')
         Swin Transformer trained on GAN + early diffusion images. Best for DALL-E 2,
         Stable Diffusion 1.x/2.x, and overall scene-level synthetic detection.

      2. Facial Deepfake & Manipulation Specialist ('dima806/deepfake_vs_real_image_detection')
         Vision Transformer fine-tuned for facial deepfakes and face-swap manipulation.

      3. Modern Diffusion Specialist ('Organika/sdxl-detector')
         Swin-B model specifically targeting Stable Diffusion XL, Flux, Midjourney v6,
         and ChatGPT-4o image outputs. Fills the accuracy gap in the older models.

    Ensemble Logic (Weighted Vote):
      - Model 1 (umm-maybe): weight 0.40  — broad GAN/diffusion coverage
      - Model 2 (dima806):   weight 0.25  — facial deepfake coverage
      - Model 3 (Organika):  weight 0.35  — modern high-quality diffusion coverage
    - If any model fires strongly (>= 0.75), its signal is amplified in the fusion.
    - Individual model telemetry preserved in sub_models for transparency.
    - 100% local, zero-cloud data transmission.
    """

    # Ensemble weights per model — must sum to 1.0
    _MODEL_WEIGHTS = {
        "generative_diffusion":   0.40,
        "facial_deepfake":        0.25,
        "modern_diffusion":       0.35,
    }

    def __init__(self):
        self.generative_model_name = settings.HF_GENERATIVE_MODEL_NAME
        self.deepfake_model_name = settings.HF_DEEPFAKE_MODEL_NAME
        self.model_name = settings.HF_MODEL_NAME
        self.model_revision = settings.HF_MODEL_REVISION

        # Runner 1: Broad generative detection (Swin Transformer)
        self.gen_runner = SingleModelRunner(
            model_name=self.generative_model_name,
            model_revision="",
            role="GENERATIVE_DIFFUSION"
        )
        # Runner 2: Facial deepfake specialist (ViT)
        self.deepfake_runner = SingleModelRunner(
            model_name=self.deepfake_model_name,
            model_revision="29e4cf9efc543845610045f6ba7e88e5cf9d9301",
            role="FACIAL_DEEPFAKE"
        )
        # Runner 3: Modern diffusion specialist (Swin-B, SDXL / Flux / MJ v6)
        self.sdxl_runner = SingleModelRunner(
            model_name="Organika/sdxl-detector",
            model_revision="",
            role="MODERN_DIFFUSION"
        )

        # Backwards compatibility attributes for unit test mocks
        self._processor = None
        self._model = None
        self._device = None
        self._id2label = None
        self._is_loaded = None
        self._load_error = None

    @staticmethod
    def _classify_label_defensively(raw_label: str) -> str:
        """
        Normalizes classification labels defensively across model architectures.
        Matches common synthetic vs real synonyms (including 'artificial' and 'human').
        """
        clean = str(raw_label).strip().lower()
        if any(term in clean for term in ["artificial", "fake", "manipulated", "synthetic", "generated", "deepfake", "ai_generated", "ai"]):
            return "MANIPULATED"
        if any(term in clean for term in ["human", "real", "authentic", "pristine", "original", "natural"]):
            return "UNMANIPULATED"
        return "UNKNOWN"

    def load_model(self) -> bool:
        """Pre-loads configured models."""
        if self._is_loaded is False:
            return False
        g_ok = self.gen_runner.load_model()
        d_ok = self.deepfake_runner.load_model()
        s_ok = self.sdxl_runner.load_model()
        return g_ok or d_ok or s_ok

    def _weighted_ensemble_vote(
        self,
        gen_ind: Optional[float],
        df_ind: Optional[float],
        sdxl_ind: Optional[float],
    ) -> Tuple[float, str]:
        """
        Fuses three model indicators into a single ensemble indicator using
        calibrated weighted averaging with strong-signal amplification.

        Returns: (ensemble_indicator, active_role_description)
        """
        w = self._MODEL_WEIGHTS
        parts = []
        roles = []

        if gen_ind is not None:
            parts.append((gen_ind, w["generative_diffusion"], "umm-maybe/AI-image-detector"))
            roles.append(f"GEN:{gen_ind:.2f}")
        if df_ind is not None:
            parts.append((df_ind, w["facial_deepfake"], "dima806/deepfake_vs_real"))
            roles.append(f"DF:{df_ind:.2f}")
        if sdxl_ind is not None:
            parts.append((sdxl_ind, w["modern_diffusion"], "Organika/sdxl-detector"))
            roles.append(f"SDXL:{sdxl_ind:.2f}")

        if not parts:
            return 0.0, "No models available"

        # Normalize weights to available models
        total_w = sum(p[1] for p in parts)
        base_ind = sum(p[0] * (p[1] / total_w) for p in parts)

        # Strong-signal amplification: if any single model fires >= 0.75, boost the ensemble
        strong_signals = [p for p in parts if p[0] >= 0.75]
        if strong_signals:
            # Take max strong signal and blend it 60/40 with base
            max_strong = max(p[0] for p in strong_signals)
            ensemble_ind = round((max_strong * 0.60) + (base_ind * 0.40), 4)
        else:
            ensemble_ind = round(base_ind, 4)

        return min(1.0, ensemble_ind), " | ".join(roles)

    def predict(self, image_input: Any) -> Dict[str, Any]:
        """
        Executes multi-model neural vision inference on an image file path or PIL Image object.
        Returns unified indicator alongside granular sub-model findings.
        """
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Check if model loading explicitly failed or was mocked to fail
        if self._is_loaded is False:
            return {
                "ai_model_name": self.model_name,
                "ai_model_version": self.model_revision or "latest",
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": "ANALYSIS UNAVAILABLE",
                "label_mapping": self._id2label or {},
                "predicted_label": None,
                "runtime_device": str(self._device) if self._device else "unknown",
                "inference_timestamp": timestamp,
                "error_detail": f"Local ML inference unavailable: {self._load_error or 'Offline'}"
            }

        # 1. Load & Validate Image
        try:
            if isinstance(image_input, (str, Path)):
                img = Image.open(image_input).convert("RGB")
            elif isinstance(image_input, Image.Image):
                img = image_input.convert("RGB")
            else:
                raise ValueError("Invalid image input type.")
        except Exception as e:
            return {
                "ai_model_name": "Multi-Model Neural Vision Ensemble",
                "ai_model_version": "3.0-TripleEngine",
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": "ERROR",
                "label_mapping": {},
                "predicted_label": None,
                "runtime_device": "unknown",
                "inference_timestamp": timestamp,
                "error_detail": f"Malformed or unreadable image stream: {e}"
            }

        # 2. Check for single mocked model (unit test mode)
        if self._model is not None:
            mock_runner = SingleModelRunner(self.model_name, self.model_revision)
            mock_runner._model = self._model
            mock_runner._processor = self._processor
            mock_runner._device = self._device or "cpu"
            mock_runner._id2label = self._id2label or {0: "REAL", 1: "FAKE"}
            mock_runner._is_loaded = True
            return mock_runner.predict(img)

        # 3. Triple-Model Inference (in parallel-compatible order)
        gen_res  = self.gen_runner.predict(img)
        df_res   = self.deepfake_runner.predict(img)
        sdxl_res = self.sdxl_runner.predict(img)

        sub_models = {
            "generative_diffusion_detector": gen_res,
            "facial_deepfake_detector":      df_res,
            "modern_diffusion_detector":     sdxl_res,
        }

        # 4. Determine Ensemble Availability
        available_results = [
            r for r in [gen_res, df_res, sdxl_res]
            if r.get("model_status") == "AVAILABLE" and r.get("ai_manipulation_indicator") is not None
        ]

        if not available_results:
            status = "ANALYSIS INCONCLUSIVE" if any(
                r.get("model_status") == "ANALYSIS INCONCLUSIVE" for r in [gen_res, df_res, sdxl_res]
            ) else "ANALYSIS UNAVAILABLE"
            return {
                "ai_model_name": "Multi-Model Neural Vision Ensemble",
                "ai_model_version": "3.0-TripleEngine",
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": status,
                "label_mapping": {},
                "predicted_label": None,
                "runtime_device": gen_res.get("runtime_device", "cpu"),
                "inference_timestamp": timestamp,
                "sub_models": sub_models,
                "error_detail": gen_res.get("error_detail") or df_res.get("error_detail") or "All vision models unavailable"
            }

        # 5. Weighted Ensemble Fusion
        gen_ind  = gen_res.get("ai_manipulation_indicator")  if gen_res.get("model_status")  == "AVAILABLE" else None
        df_ind   = df_res.get("ai_manipulation_indicator")   if df_res.get("model_status")   == "AVAILABLE" else None
        sdxl_ind = sdxl_res.get("ai_manipulation_indicator") if sdxl_res.get("model_status") == "AVAILABLE" else None

        ensemble_ind, active_role = self._weighted_ensemble_vote(gen_ind, df_ind, sdxl_ind)

        # Ensemble confidence: average of available model confidences
        conf_values = [
            r.get("model_confidence") for r in [gen_res, df_res, sdxl_res]
            if r.get("model_status") == "AVAILABLE" and r.get("model_confidence") is not None
        ]
        ensemble_conf = round(sum(conf_values) / len(conf_values), 4) if conf_values else 0.80

        predicted_lbl = "MANIPULATED" if ensemble_ind >= 0.50 else "UNMANIPULATED"

        return {
            "ai_model_name": "Multi-Model Neural Vision Ensemble",
            "ai_model_version": "3.0-TripleEngine",
            "ai_manipulation_indicator": ensemble_ind,
            "model_confidence": ensemble_conf,
            "model_status": "AVAILABLE",
            "label_mapping": {"0": "UNMANIPULATED", "1": "MANIPULATED"},
            "predicted_label": predicted_lbl,
            "raw_label": active_role,
            "runtime_device": gen_res.get("runtime_device", "cpu"),
            "inference_timestamp": timestamp,
            "sub_models": sub_models,
            "error_detail": None
        }
