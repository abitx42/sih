import pytest
import tempfile
from unittest.mock import MagicMock, patch
from pathlib import Path
import numpy as np
from PIL import Image

from app.analyzers.video_analyzer import VideoAnalyzer

def test_mock_successful_frame_aggregation():
    """
    Test successful frame decoding and median AI indicator aggregation across sampled frames.
    """
    analyzer = VideoAnalyzer()
    
    # Mock decoded frames (8 frames)
    mock_frames = [Image.new("RGB", (100, 100), color=(i * 20, 50, 100)) for i in range(8)]
    mock_metadata = {
        "total_frames_in_stream": 120,
        "fps": 30.0,
        "duration_seconds": 4.0,
        "sampled_frame_indices": [0, 15, 30, 45, 60, 75, 90, 105],
        "frame_timestamps": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
        "video_resolution": "100x100"
    }

    # Mock HFImageDetector predicting varying frame-level scores
    # Frame indicators: [0.80, 0.82, 0.85, 0.88, 0.90, 0.92, 0.84, 0.86] -> Median: ~0.855
    mock_predictions = [
        {"model_status": "AVAILABLE", "ai_manipulation_indicator": ind, "model_confidence": 0.92}
        for ind in [0.80, 0.82, 0.85, 0.88, 0.90, 0.92, 0.84, 0.86]
    ]

    with patch.object(analyzer, "_decode_and_sample_frames", return_value=(mock_frames, mock_metadata)), \
         patch.object(analyzer.hf_detector, "predict", side_effect=mock_predictions):
        
        res = analyzer.analyze(Path("dummy_video.mp4"), "EV-VID-001")

        assert res["model_status"] == "AVAILABLE"
        assert res["ai_manipulation_indicator"] is not None
        assert 0.84 <= res["ai_manipulation_indicator"] <= 0.87
        assert res["raw_metrics"]["sampled_frames_count"] == 8
        assert res["raw_metrics"]["ml_detector"]["analysed_frame_count"] == 8
        assert res["raw_metrics"]["ml_detector"]["median_ai_indicator"] is not None
        assert res["raw_metrics"]["ml_detector"]["iqr_ai_indicator"] is not None
        assert len(res["findings"]) >= 2  # Temporal heuristic finding + ML finding

def test_decoder_failure_returns_analysis_unavailable():
    """
    When video cannot be opened or decoded (0 frames), the system returns
    ANALYSIS UNAVAILABLE and never creates simulated/fallback scores.
    """
    analyzer = VideoAnalyzer()

    with patch.object(analyzer, "_decode_and_sample_frames", return_value=([], {"total_frames_in_stream": 0})):
        res = analyzer.analyze(Path("corrupted_video.mp4"), "EV-VID-002")

        assert res["model_status"] == "ANALYSIS UNAVAILABLE"
        assert res["ai_manipulation_indicator"] is None
        assert res["model_confidence"] is None
        assert res["forensic_anomaly_score"] == 0.0
        assert res["raw_metrics"]["sampled_frames_count"] == 0
        assert any("ANALYSIS UNAVAILABLE" in f["signal_name"] for f in res["findings"])

def test_fewer_than_3_valid_frames_returns_inconclusive():
    """
    If fewer than 3 frames are decoded or produced valid ML outputs,
    the system marks the analysis INCONCLUSIVE with no invented value.
    """
    analyzer = VideoAnalyzer()
    
    # Only 2 frames available
    mock_frames = [Image.new("RGB", (64, 64)), Image.new("RGB", (64, 64))]
    mock_metadata = {
        "total_frames_in_stream": 2,
        "fps": 25.0,
        "sampled_frame_indices": [0, 1],
        "frame_timestamps": [0.0, 0.04]
    }

    mock_predictions = [
        {"model_status": "AVAILABLE", "ai_manipulation_indicator": 0.75, "model_confidence": 0.88},
        {"model_status": "AVAILABLE", "ai_manipulation_indicator": 0.80, "model_confidence": 0.90}
    ]

    with patch.object(analyzer, "_decode_and_sample_frames", return_value=(mock_frames, mock_metadata)), \
         patch.object(analyzer.hf_detector, "predict", side_effect=mock_predictions):
        
        res = analyzer.analyze(Path("short_video.mp4"), "EV-VID-003")

        assert res["model_status"] == "ANALYSIS INCONCLUSIVE"
        assert res["ai_manipulation_indicator"] is None
        assert res["raw_metrics"]["sampled_frames_count"] == 2
        assert res["raw_metrics"]["ml_detector"]["analysed_frame_count"] == 2
        assert any("INCONCLUSIVE" in f["signal_name"] for f in res["findings"])

def test_unknown_model_labels_on_video_frames_returns_inconclusive():
    """
    If all frame predictions return ANALYSIS INCONCLUSIVE due to unknown labels,
    the aggregated video result must be ANALYSIS INCONCLUSIVE.
    """
    analyzer = VideoAnalyzer()
    mock_frames = [Image.new("RGB", (64, 64)) for _ in range(5)]
    mock_metadata = {
        "total_frames_in_stream": 50,
        "fps": 25.0,
        "sampled_frame_indices": [0, 10, 20, 30, 40],
        "frame_timestamps": [0.0, 0.4, 0.8, 1.2, 1.6]
    }

    inconclusive_pred = {
        "model_status": "ANALYSIS INCONCLUSIVE",
        "ai_manipulation_indicator": None,
        "model_confidence": 0.65,
        "predicted_label": "UNKNOWN"
    }

    with patch.object(analyzer, "_decode_and_sample_frames", return_value=(mock_frames, mock_metadata)), \
         patch.object(analyzer.hf_detector, "predict", return_value=inconclusive_pred):
        
        res = analyzer.analyze(Path("dummy.mp4"), "EV-VID-004")

        assert res["model_status"] == "ANALYSIS INCONCLUSIVE"
        assert res["ai_manipulation_indicator"] is None
        assert res["raw_metrics"]["ml_detector"]["analysed_frame_count"] == 0
        assert res["raw_metrics"]["ml_detector"]["inconclusive_frame_count"] == 5

@pytest.mark.slow
def test_real_video_opencv_decoding_and_analysis_integration():
    """
    Integration test: creates a real synthetic MP4 video on disk using OpenCV VideoWriter,
    executes real video decoding and frame sampling (max 16 frames), and verifies pipeline execution.
    """
    import cv2
    analyzer = VideoAnalyzer()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        temp_video_path = Path(f.name)

    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        fps = 20.0
        width, height = 160, 120
        out = cv2.VideoWriter(str(temp_video_path), fourcc, fps, (width, height))

        # Generate 25 synthetic frames with slight color progression
        for i in range(25):
            frame = np.full((height, width, 3), (i * 8, 100, 150), dtype=np.uint8)
            cv2.putText(frame, f"F{i}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            out.write(frame)
        out.release()

        # Run analysis
        res = analyzer.analyze(temp_video_path, "EV-VID-REAL-001")

        assert "model_status" in res
        assert "forensic_anomaly_score" in res
        assert res["raw_metrics"]["sampled_frames_count"] > 0
        assert res["raw_metrics"]["sampled_frames_count"] <= 16
        assert len(res["raw_metrics"]["frame_timestamps"]) == res["raw_metrics"]["sampled_frames_count"]
        assert len(res["findings"]) >= 2
    finally:
        if temp_video_path.exists():
            temp_video_path.unlink()
