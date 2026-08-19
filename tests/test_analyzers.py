import tempfile
import numpy as np
from PIL import Image
from pathlib import Path
from app.analyzers.image_analyzer import ImageAnalyzer
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
