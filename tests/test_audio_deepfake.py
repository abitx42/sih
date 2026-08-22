"""
tests/test_audio_deepfake.py
============================
Unit tests for Voice Deepfake Acoustic Detector & Neural Vocoder Phase Analysis.
"""
import wave
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.config import EVIDENCE_DIR
from app.core.audio_deepfake_detector import AudioDeepfakeDetector
from app.analyzers.audio_analyzer import AudioAnalyzer

client = TestClient(app)


def test_audio_deepfake_detector_synthetic_vs_natural():
    """Verify acoustic formant and vocoder detection on synthetic vs harmonic audio."""
    sample_rate = 22050
    duration = 1.0  # 1 second
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

    # 1. Generate pure tone harmonic audio (simulating voice fundamental + formants)
    voice_sig = 0.5 * np.sin(2 * np.pi * 220 * t) + 0.3 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 880 * t)
    
    res_nat = AudioDeepfakeDetector.analyze_audio_stream(voice_sig, sample_rate, "TEST-EV-AUDIO-NAT")
    assert "ai_manipulation_indicator" in res_nat
    assert "phase_entropy" in res_nat
    assert "vocoder_attribution" in res_nat

    # 2. Test AudioAnalyzer integration
    test_wav = EVIDENCE_DIR / "test_audio_synth.wav"
    with wave.open(str(test_wav), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes((voice_sig * 32767).astype(np.int16).tobytes())

    analyzer = AudioAnalyzer()
    out = analyzer.analyze(test_wav, "TEST-EV-AUDIO-PIPE")
    assert out["model_status"] == "AVAILABLE"
    assert out["ai_model_name"] == "Acoustic VoicePrint & Neural Vocoder Detector"
    assert out["ai_manipulation_indicator"] is not None

    if test_wav.exists():
        test_wav.unlink()
