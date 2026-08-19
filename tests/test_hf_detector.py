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
    assert detector._classify_label_defensively("Real") == "UNMANIPULATED"
    assert detector._classify_label_defensively("AI_Generated") == "MANIPULATED"
    assert detector._classify_label_defensively("CustomClassXYZ") == "UNKNOWN"

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
    else:
        assert res["ai_manipulation_indicator"] is None
