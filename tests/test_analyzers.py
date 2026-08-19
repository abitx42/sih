import tempfile
import numpy as np
from PIL import Image
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.analyzers.image_analyzer import ImageAnalyzer
from app.analyzers.video_analyzer import VideoAnalyzer
from app.analyzers.audio_analyzer import AudioAnalyzer
from app.analyzers.document_analyzer import DocumentAnalyzer

def test_image_analyzer_execution():
    analyzer = ImageAnalyzer()
    
    # Create test image
    img = Image.new("RGB", (256, 256), color=(73, 109, 137))
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        img.save(f.name, "JPEG")
        temp_path = Path(f.name)

    try:
        res = analyzer.analyze(temp_path, "EV-TEST-001")
        assert "forensic_anomaly_score" in res
        assert "model_status" in res
        assert "ai_model_name" in res
        assert "findings" in res
        assert len(res["findings"]) > 0
        assert "raw_metrics" in res
        assert "ela_image_path" in res["raw_metrics"]
        assert "fft_image_path" in res["raw_metrics"]
    finally:
        if temp_path.exists():
            temp_path.unlink()

def test_video_analyzer_execution():
    analyzer = VideoAnalyzer()
    mock_frames = [Image.new("RGB", (64, 64), color=(i * 30, 100, 120)) for i in range(4)]
    mock_meta = {
        "total_frames_in_stream": 40,
        "fps": 20.0,
        "sampled_frame_indices": [0, 10, 20, 30],
        "frame_timestamps": [0.0, 0.5, 1.0, 1.5]
    }
    
    mock_predictions = [
        {"model_status": "AVAILABLE", "ai_manipulation_indicator": 0.15, "model_confidence": 0.94}
        for _ in range(4)
    ]

    with patch.object(analyzer, "_decode_and_sample_frames", return_value=(mock_frames, mock_meta)), \
         patch.object(analyzer.hf_detector, "predict", side_effect=mock_predictions):
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00\x00\x00 ftypmp42\x00\x00\x00\x00isommp42")
            temp_path = Path(f.name)

        try:
            res = analyzer.analyze(temp_path, "EV-TEST-VID")
            assert res["model_status"] == "AVAILABLE"
            assert res["ai_manipulation_indicator"] == 0.15
            assert "forensic_anomaly_score" in res
            assert len(res["findings"]) >= 2
        finally:
            if temp_path.exists():
                temp_path.unlink()

def test_document_analyzer_pdf():
    analyzer = DocumentAnalyzer()
    
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Producer (ForensicTestApp) >>\nendobj\n%%EOF\n"
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_content)
        temp_path = Path(f.name)

    try:
        res = analyzer.analyze(temp_path, "EV-TEST-002")
        assert "ai_manipulation_score" in res
        assert "findings" in res
        assert res["raw_metrics"]["eof_markers_count"] == 1
    finally:
        if temp_path.exists():
            temp_path.unlink()
