import pytest
import tempfile
from unittest.mock import MagicMock, patch
from pathlib import Path
from PIL import Image
import torch

from app.analyzers.hf_image_detector import HFImageDetector
from app.config import settings
from app.core.risk_engine import RiskEngine

def test_mock_successful_manipulated_prediction():
    """
    Test successful inference returning MANIPULATED label and indicator.
    """
    detector = HFImageDetector()
    detector._is_loaded = True
    detector._device = "cpu"
    detector._id2label = {0: "REAL", 1: "FAKE"}
    
    mock_processor = MagicMock()
    mock_processor.return_tensors = "pt"
    mock_processor.return_value = {"pixel_values": torch.zeros((1, 3, 224, 224))}
    detector._processor = mock_processor

    mock_model = MagicMock()
    mock_outputs = MagicMock()
    mock_outputs.logits = torch.tensor([[-2.5, 4.5]])
    mock_model.return_value = mock_outputs
    detector._model = mock_model

    img = Image.new("RGB", (100, 100), color=(200, 100, 50))
    res = detector.predict(img)

    assert res["model_status"] == "AVAILABLE"
    assert res["ai_manipulation_indicator"] is not None
    assert res["ai_manipulation_indicator"] > 0.90
    assert res["model_confidence"] is not None
    assert res["predicted_label"] == "MANIPULATED"
    assert res["runtime_device"] == "cpu"
    assert res["error_detail"] is None

def test_mock_successful_unmanipulated_prediction():
    """
    Test successful inference returning UNMANIPULATED label and low indicator.
    """
    detector = HFImageDetector()
    detector._is_loaded = True
    detector._device = "cpu"
    detector._id2label = {0: "authentic", 1: "synthetic"}

    mock_processor = MagicMock()
    mock_processor.return_value = {"pixel_values": torch.zeros((1, 3, 224, 224))}
    detector._processor = mock_processor

    mock_model = MagicMock()
    mock_outputs = MagicMock()
    mock_outputs.logits = torch.tensor([[5.0, -3.0]])
    mock_model.return_value = mock_outputs
    detector._model = mock_model

    img = Image.new("RGB", (100, 100), color=(50, 150, 200))
    res = detector.predict(img)

    assert res["model_status"] == "AVAILABLE"
    assert res["ai_manipulation_indicator"] is not None
    assert res["ai_manipulation_indicator"] < 0.10
    assert res["predicted_label"] == "UNMANIPULATED"

def test_unknown_label_map_returns_analysis_inconclusive():
    """
    Test that when model class labels cannot be mapped to MANIPULATED/UNMANIPULATED,
    it returns ANALYSIS INCONCLUSIVE with ai_manipulation_indicator: None and does not guess 1 - top_prob.
    """
    detector = HFImageDetector()
    detector._is_loaded = True
    detector._device = "cpu"
    # Unmapped arbitrary labels
    detector._id2label = {0: "category_alpha", 1: "category_beta"}

    mock_processor = MagicMock()
    mock_processor.return_value = {"pixel_values": torch.zeros((1, 3, 224, 224))}
    detector._processor = mock_processor

    mock_model = MagicMock()
    mock_outputs = MagicMock()
    mock_outputs.logits = torch.tensor([[2.0, 8.0]])
    mock_model.return_value = mock_outputs
    detector._model = mock_model

    img = Image.new("RGB", (80, 80))
    res = detector.predict(img)

    assert res["model_status"] == "ANALYSIS INCONCLUSIVE"
    assert res["ai_manipulation_indicator"] is None
    assert res["model_confidence"] is not None
    assert res["predicted_label"] == "UNKNOWN"
    assert "could not be safely mapped" in res["error_detail"]

def test_model_unavailable_returns_analysis_unavailable():
    """
    Test that when model loading fails, the system returns ANALYSIS UNAVAILABLE
    and never invents or fabricates an indicator score.
    """
    detector = HFImageDetector()
    detector._is_loaded = False

    with patch.object(detector, "load_model", return_value=False):
        detector._load_error = "Connection refused: offline environment"
        img = Image.new("RGB", (50, 50))
        res = detector.predict(img)

        assert res["model_status"] == "ANALYSIS UNAVAILABLE"
        assert res["ai_manipulation_indicator"] is None
        assert res["model_confidence"] is None
        assert res["predicted_label"] is None
        assert "unavailable" in res["error_detail"].lower()

def test_malformed_image_input_returns_error():
    """
    Test handling of invalid/corrupted image file paths.
    """
    detector = HFImageDetector()
    detector._is_loaded = True
    detector._device = "cpu"
    detector._model = MagicMock()

    res = detector.predict("non_existent_corrupted_image.png")
    assert res["model_status"] == "ERROR"
    assert res["ai_manipulation_indicator"] is None
    assert res["error_detail"] is not None

def test_coe_gateway_configuration_defaults():
    """
    Test that TCET CoE AI Gateway defaults are correctly configured.
    """
    assert "tcetcercd.in" in settings.LLM_API_BASE_URL
    assert settings.LLM_MODEL == "qwen3.6"
    assert isinstance(settings.LLM_API_KEY, str)

def test_risk_engine_inconclusive_defaults_to_review_required():
    """
    Test that when model_status is ANALYSIS INCONCLUSIVE, RiskEngine defaults to REVIEW REQUIRED.
    """
    score, category, conf, comps = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=None,
        model_status="ANALYSIS INCONCLUSIVE",
        forensic_anomaly_score=15.0,
        metadata_anomaly_score=10.0,
        provenance_status="VERIFIED",
        findings=[]
    )
    assert category == "REVIEW REQUIRED"
    assert score >= 35.0
    assert comps["model_status"] == "ANALYSIS INCONCLUSIVE"
    assert comps["ai_manipulation_risk"] is None

def test_defensive_label_normalization():
    detector = HFImageDetector()
    assert detector._classify_label_defensively("deepfake") == "MANIPULATED"
    assert detector._classify_label_defensively("artificial") == "MANIPULATED"
    assert detector._classify_label_defensively("Real") == "UNMANIPULATED"
    assert detector._classify_label_defensively("human") == "UNMANIPULATED"
    assert detector._classify_label_defensively("AI_Generated") == "MANIPULATED"
    assert detector._classify_label_defensively("CustomClassXYZ") == "UNKNOWN"

def test_multi_model_vision_ensemble_structure():
    """
    Verifies that HFImageDetector instantiates all 5 specialized sub-model runners:
    Smogy (modern diffusion), Organika SDXL, dima806 general AI vs real,
    umm-maybe legacy generative, and dima806 facial deepfake.
    """
    detector = HFImageDetector()
    # Core runners that must exist
    assert hasattr(detector, "smogy_runner")
    assert hasattr(detector, "sdxl_runner")
    assert hasattr(detector, "general_runner")
    assert hasattr(detector, "gen_runner")
    assert hasattr(detector, "deepfake_runner")
    # Check roles
    assert detector.smogy_runner.role == "MODERN_DIFFUSION_SMOGY"
    assert detector.sdxl_runner.role == "MODERN_DIFFUSION_ORGANIKA"
    assert detector.general_runner.role == "GENERAL_AI_VS_REAL"
    assert detector.gen_runner.role == "GENERATIVE_DIFFUSION_LEGACY"
    assert detector.deepfake_runner.role == "FACIAL_DEEPFAKE"
    # Weights must sum to 1.0
    weight_sum = sum(detector._MODEL_WEIGHTS.values())
    assert abs(weight_sum - 1.0) < 0.001, f"Model weights sum to {weight_sum}, expected 1.0"

def test_weighted_ensemble_vote():
    """
    Verifies 5-model calibrated ensemble fusion logic:
    - _calibrated_ensemble_vote replaces the old _weighted_ensemble_vote
    - Low scores produce low ensemble indicator
    - High-agreement models produce high ensemble indicator
    - Partial availability (None values) are handled gracefully
    """
    detector = HFImageDetector()

    # New method name is _calibrated_ensemble_vote
    assert hasattr(detector, "_calibrated_ensemble_vote"), \
        "HFImageDetector must have _calibrated_ensemble_vote method"

    # Signature: List[Tuple[indicator: float, weight: float, role: str]] -> (ensemble, roles_str, metadata)

    # 1. All low scores -> low ensemble indicator
    ind_low, _, _ = detector._calibrated_ensemble_vote([
        (0.10, 0.28, "MODERN_DIFFUSION_SMOGY"),
        (0.15, 0.22, "MODERN_DIFFUSION_ORGANIKA"),
        (0.12, 0.22, "GENERAL_AI_VS_REAL"),
        (0.18, 0.16, "GENERATIVE_DIFFUSION_LEGACY"),
        (0.10, 0.12, "FACIAL_DEEPFAKE"),
    ])
    assert ind_low < 0.35, f"Low scores should produce low ensemble, got {ind_low}"

    # 2. All high scores -> high ensemble indicator (agreement bonus applies)
    ind_high, _, meta = detector._calibrated_ensemble_vote([
        (0.85, 0.28, "MODERN_DIFFUSION_SMOGY"),
        (0.90, 0.22, "MODERN_DIFFUSION_ORGANIKA"),
        (0.88, 0.22, "GENERAL_AI_VS_REAL"),
        (0.80, 0.16, "GENERATIVE_DIFFUSION_LEGACY"),
        (0.82, 0.12, "FACIAL_DEEPFAKE"),
    ])
    assert ind_high >= 0.80, f"High agreement scores should produce high ensemble, got {ind_high}"

    # 3. Partial availability (fewer models)
    ind_partial, _, _ = detector._calibrated_ensemble_vote([
        (0.85, 0.28, "MODERN_DIFFUSION_SMOGY"),
        (0.90, 0.22, "MODERN_DIFFUSION_ORGANIKA"),
    ])
    assert ind_partial >= 0.75, f"High partial scores should still be high, got {ind_partial}"

    # 4. Mixed scores -> disagreement penalty may apply
    ind_mixed, _, _ = detector._calibrated_ensemble_vote([
        (0.10, 0.28, "MODERN_DIFFUSION_SMOGY"),
        (0.90, 0.22, "MODERN_DIFFUSION_ORGANIKA"),
        (0.15, 0.22, "GENERAL_AI_VS_REAL"),
        (0.85, 0.16, "GENERATIVE_DIFFUSION_LEGACY"),
        (0.12, 0.12, "FACIAL_DEEPFAKE"),
    ])
    assert 0.0 <= ind_mixed <= 1.0

@pytest.mark.slow
def test_real_model_local_inference_smoke():
    """
    Optional integration test: attempts real model loading if weights are available.
    Verifies valid schema output and that offline/missing weights gracefully return ANALYSIS UNAVAILABLE.
    """
    detector = HFImageDetector()
    img = Image.new("RGB", (64, 64), color=(120, 120, 120))
    res = detector.predict(img)

    assert "model_status" in res
    assert res["model_status"] in ["AVAILABLE", "ANALYSIS UNAVAILABLE", "ANALYSIS INCONCLUSIVE", "ERROR"]
    if res["model_status"] == "AVAILABLE":
        assert isinstance(res["ai_manipulation_indicator"], float)
        assert 0.0 <= res["ai_manipulation_indicator"] <= 1.0
        assert "sub_models" in res
    else:
        assert res["ai_manipulation_indicator"] is None
