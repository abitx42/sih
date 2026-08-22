import pytest
import io
import wave
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image

from app.analyzers.audio_analyzer import AudioAnalyzer
from app.core.risk_engine import RiskEngine

def generate_test_wav(
    duration: float = 1.5,
    sample_rate: int = 22050,
    freq: float = 440.0,
    with_splice: bool = False,
    with_silence: bool = False,
    with_clipping: bool = False
) -> bytes:
    """Helper to generate clean or manipulated WAV byte streams for testing."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    if with_splice:
        # Construct audio with sharp energy and frequency steps
        t1 = t[: len(t) // 3]
        t2 = t[len(t) // 3 : 2 * len(t) // 3]
        t3 = t[2 * len(t) // 3 :]
        s1 = 0.5 * np.sin(2 * np.pi * 300 * t1)
        s2 = np.zeros_like(t2)  # silence step
        s3 = 0.9 * np.sin(2 * np.pi * 3500 * t3)  # high frequency burst
        signal_data = np.concatenate([s1, s2, s3])
    elif with_silence:
        signal_data = 0.4 * np.sin(2 * np.pi * freq * t)
        signal_data[int(0.3 * sample_rate) : int(0.9 * sample_rate)] = 0.0  # 600ms silence
    else:
        signal_data = 0.5 * np.sin(2 * np.pi * freq * t)

    if with_clipping:
        signal_data = np.clip(signal_data * 5.0, -0.999, 0.999)

    audio_int16 = (signal_data * 32767.0).astype(np.int16)
    
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_f:
        wav_f.setnchannels(1)
        wav_f.setsampwidth(2)
        wav_f.setframerate(sample_rate)
        wav_f.writeframes(audio_int16.tobytes())
    
    return wav_io.getvalue()

def test_audio_decoding_and_physical_metrics():
    """
    Test real WAV decoding, sample extraction, and physical acoustic metrics.
    """
    analyzer = AudioAnalyzer()
    wav_bytes = generate_test_wav(duration=1.0, sample_rate=22050, freq=440.0)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        temp_path = Path(f.name)

    try:
        res = analyzer.analyze(temp_path, "EV-AUD-001")

        assert res["model_status"] in ["AVAILABLE", "ANALYSIS UNAVAILABLE"]
        assert "forensic_anomaly_score" in res
        
        metrics = res["raw_metrics"]
        assert metrics["codec"] == "PCM_WAV"
        assert metrics["sample_rate_hz"] == 22050
        assert metrics["channels"] == 1
        assert 0.95 <= metrics["duration_seconds"] <= 1.05
        assert metrics["bit_depth"] == 16
        assert metrics["decoded_sample_count"] == 22050
        assert "spectral_centroid_hz" in metrics
        assert "spectral_rolloff_hz" in metrics
        assert "rms_energy_mean" in metrics
    finally:
        if temp_path.exists():
            temp_path.unlink()

def test_waveform_and_spectrogram_rendering():
    """
    Test that waveform and spectrogram visualization exhibits are generated and saved as valid PNGs.
    """
    analyzer = AudioAnalyzer()
    wav_bytes = generate_test_wav(duration=1.2, sample_rate=22050, freq=500.0)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        temp_path = Path(f.name)

    try:
        res = analyzer.analyze(temp_path, "EV-AUD-002")
        metrics = res["raw_metrics"]

        waveform_file = Path(metrics["waveform_path"])
        spectrogram_file = Path(metrics["spectrogram_path"])

        assert waveform_file.exists()
        assert spectrogram_file.exists()

        # Check valid image headers
        with Image.open(waveform_file) as img:
            assert img.format == "PNG"
            assert img.size[0] >= 400
        
        with Image.open(spectrogram_file) as img:
            assert img.format == "PNG"
            assert img.size[0] >= 400
    finally:
        if temp_path.exists():
            temp_path.unlink()

def test_silence_and_splice_candidate_detection():
    """
    Test detection of abrupt energy/spectral step transitions and silence intervals.
    """
    analyzer = AudioAnalyzer()
    wav_bytes = generate_test_wav(duration=2.0, sample_rate=22050, with_splice=True, with_clipping=True)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        temp_path = Path(f.name)

    try:
        res = analyzer.analyze(temp_path, "EV-AUD-003")
        metrics = res["raw_metrics"]

        assert metrics["splice_candidate_count"] > 0
        assert metrics["clipping_ratio"] > 0.0
        assert len(res["findings"]) >= 2
        # Verify findings include cautious disclaimers
        assert any("manual review" in f["explanation"].lower() or "physical" in f["explanation"].lower() for f in res["findings"])
    finally:
        if temp_path.exists():
            temp_path.unlink()

def test_malformed_audio_returns_analysis_unavailable():
    """
    Test that corrupted/empty audio files return ANALYSIS UNAVAILABLE with zero fabricated metrics.
    """
    analyzer = AudioAnalyzer()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00corrupteddata")
        temp_path = Path(f.name)

    try:
        res = analyzer.analyze(temp_path, "EV-AUD-CORRUPT")

        assert res["model_status"] == "ANALYSIS UNAVAILABLE"
        assert res["ai_manipulation_indicator"] is None
        assert res["forensic_anomaly_score"] == 0.0
        assert res["raw_metrics"]["decoded_sample_count"] == 0
        assert any("ANALYSIS UNAVAILABLE" in f["signal_name"] for f in res["findings"])
    finally:
        if temp_path.exists():
            temp_path.unlink()

def test_risk_engine_behaviour_when_audio_ml_unavailable():
    """
    Test that RiskEngine correctly marks audio with unavailable ML as REVIEW REQUIRED.
    """
    score, category, conf, comps = RiskEngine.calculate_risk(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=None,
        model_status="ANALYSIS UNAVAILABLE",
        forensic_anomaly_score=18.0,
        metadata_anomaly_score=10.0,
        provenance_status="NOT_AVAILABLE",
        findings=[]
    )

    assert category == "REVIEW REQUIRED"
    assert score >= 35.0
    assert comps["ai_manipulation_risk"] is None
    assert comps["model_status"] == "ANALYSIS UNAVAILABLE"

@pytest.mark.slow
def test_optional_ffmpeg_audio_integration():
    """
    Optional integration test: checks if ffmpeg decoding fallback functions when available.
    """
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not installed locally")

    analyzer = AudioAnalyzer()
    wav_bytes = generate_test_wav(duration=1.0, sample_rate=22050)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        temp_path = Path(f.name)

    try:
        data, meta = analyzer._decode_audio(temp_path)
        assert data is not None
        assert len(data) > 0
    finally:
        if temp_path.exists():
            temp_path.unlink()
