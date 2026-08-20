import io
import wave
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
        assert "chromatic_aberration_score" in res["raw_metrics"]
        assert "cfa_anomaly_score" in res["raw_metrics"]
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

def test_audio_analyzer_execution():
    analyzer = AudioAnalyzer()
    
    # Generate simple test WAV
    t = np.linspace(0, 1.0, 22050, endpoint=False)
    sig = (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_f:
        wav_f.setnchannels(1)
        wav_f.setsampwidth(2)
        wav_f.setframerate(22050)
        wav_f.writeframes(sig.tobytes())

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_io.getvalue())
        temp_path = Path(f.name)

    try:
        res = analyzer.analyze(temp_path, "EV-TEST-AUD")
        assert res["model_status"] == "ANALYSIS UNAVAILABLE"
        assert res["ai_manipulation_indicator"] is None
        assert "forensic_anomaly_score" in res
        assert "raw_metrics" in res
        assert res["raw_metrics"]["sample_rate_hz"] == 22050
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
        assert res["model_status"] == "ANALYSIS UNAVAILABLE"
        assert res["ai_manipulation_indicator"] is None
        assert "forensic_anomaly_score" in res
        assert "findings" in res
        assert res["raw_metrics"]["eof_markers_count"] == 1
    finally:
        if temp_path.exists():
            temp_path.unlink()

def test_document_analyzer_ooxml_macro_detection():
    import zipfile
    analyzer = DocumentAnalyzer()
    
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        with zipfile.ZipFile(f.name, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types></Types>")
            zf.writestr("word/vbaProject.bin", b"VBA MACRO PAYLOAD")
        temp_path = Path(f.name)

    try:
        res = analyzer.analyze(temp_path, "EV-TEST-DOCX")
        assert res["model_status"] == "ANALYSIS UNAVAILABLE"
        assert res["raw_metrics"]["has_macros"] is True
        assert any(f["signal_name"] == "Embedded VBA Macro Project Detected" for f in res["findings"])
    finally:
        if temp_path.exists():
            temp_path.unlink()

def test_archive_analyzer_execution():
    import zipfile
    from app.analyzers.archive_analyzer import ArchiveAnalyzer
    analyzer = ArchiveAnalyzer()

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        with zipfile.ZipFile(f.name, "w") as zf:
            zf.writestr("safe_document.txt", "Forensic analysis evidence text.")
            zf.writestr("script.ps1", "Write-Host 'Test';")
        temp_path = Path(f.name)

    try:
        res = analyzer.analyze(temp_path, "EV-TEST-ZIP")
        assert res["model_status"] == "ANALYSIS UNAVAILABLE"
        assert res["ai_manipulation_indicator"] is None
        assert "forensic_anomaly_score" in res
        assert len(res["findings"]) >= 1
    finally:
        if temp_path.exists():
            temp_path.unlink()

def test_provenance_engine_c2pa_detection():
    from app.core.provenance_engine import ProvenanceEngine

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"\xff\xd8\xff\xe1\x00\x18c2pa.claim_generator Adobe Photoshop 2024\x00\x00")
        temp_path = Path(f.name)

    try:
        res = ProvenanceEngine.inspect_provenance(temp_path)
        assert res["manifest_found"] is True
        assert res["status"] == "DETECTED_UNVERIFIED_MANIFEST"
        assert res["status"] != "VERIFIED"
        assert "Photoshop" in res["signer"]
    finally:
        if temp_path.exists():
            temp_path.unlink()

def test_c2pa_unverified_manifest_risk_scoring():
    from app.core.risk_engine import RiskEngine

    risk_score, risk_cat, confidence, comp_scores = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=0.10,
        model_status="AVAILABLE",
        forensic_anomaly_score=10.0,
        metadata_anomaly_score=10.0,
        provenance_status="DETECTED_UNVERIFIED_MANIFEST",
        findings=[]
    )
    # Provenance risk must be 25.0, not the 5.0 granted to verified cryptographic signatures
    assert comp_scores["provenance_risk"] == 25.0

def test_report_generator_hash_matching_integrity_display():
    from app.core.report_generator import ForensicReportGenerator

    evidence_data = {
        "evidence_id": "EV-TEST-PDF-001",
        "case_id": "CASE-TEST",
        "original_filename": "tampered_sample.png",
        "modality": "IMAGE",
        "mime_type": "image/png",
        "file_size_bytes": 1024,
        "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "sha512_hash": "",
        "md5_hash": None,
        "uploaded_by": "Test Examiner",
        "uploaded_at": "2026-08-20T00:00:00Z",
        "status": "COMPLETED"
    }

    forensic_result = {
        "result_id": "RES-001",
        "evidence_id": "EV-TEST-PDF-001",
        "integrity_status": "MISMATCH",
        "provenance_status": "DETECTED_UNVERIFIED_MANIFEST",
        "forensic_risk_score": 100.0,
        "risk_category": "HIGH RISK",
        "confidence_score": 95.0,
        "model_status": "AVAILABLE",
        "ai_manipulation_indicator": 0.20,
        "raw_metrics_json": {}
    }

    pdf_path = ForensicReportGenerator.generate_pdf(
        evidence_data=evidence_data,
        case_data={"case_id": "CASE-TEST", "title": "Test Case", "lead_investigator": "Officer"},
        forensic_result=forensic_result,
        findings=[],
        custody_events=[]
    )
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    assert pdf_bytes.startswith(b"%PDF")
