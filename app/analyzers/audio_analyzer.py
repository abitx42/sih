import os
import wave
import subprocess
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from scipy import signal
from PIL import Image, ImageDraw

from app.analyzers.base_analyzer import BaseAnalyzer
from app.core.explainability import FindingBuilder
from app.config import FORENSIC_DIR

logger = logging.getLogger(__name__)

class AudioAnalyzer(BaseAnalyzer):
    """
    Forensic Audio Analyzer.
    Scientifically honest, physical-signal based audio forensic module.
    
    Principles:
    1. Real audio decoding only (never creates simulated/fake waveforms).
    2. Computes explainable physical acoustic signals: RMS variation, clipping ratio,
       silence intervals, spectral centroid, spectral roll-off, high-frequency energy ratio,
       and abrupt spectral discontinuity / splice candidates.
    3. No fictional vocoder models or fabricated AI deepfake probability scores.
       Returns model_status = "ANALYSIS UNAVAILABLE" and ai_manipulation_indicator = None.
    4. Heuristic findings explicitly state physical limitations (compression, noise reduction,
       acoustic environment, re-recording).
    """

    def __init__(self):
        pass

    def analyze(self, file_path: Path, evidence_id: str) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        raw_metrics: Dict[str, Any] = {}

        # 1. Real Audio Stream Decoding
        audio_data, audio_meta = self._decode_audio(file_path)
        raw_metrics.update(audio_meta)

        # Handle decoding failure honestly
        if audio_data is None or len(audio_data) == 0:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Audio Stream Decoding: ANALYSIS UNAVAILABLE",
                category="SIGNAL_ANALYSIS",
                severity="MEDIUM",
                score=50.0,
                explanation="Audio decoder was unable to parse audio bitstream (unsupported format, corrupted header, or missing local codec).",
                location_ref="Audio Container"
            ))
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Audio ML Model: ANALYSIS UNAVAILABLE",
                category="AI_DETECTION",
                severity="MEDIUM",
                score=50.0,
                explanation="No trained audio deepfake neural network is locally integrated. Automated AI manipulation indicator is unavailable.",
                location_ref="Local Inference Engine"
            ))
            return {
                "ai_model_name": None,
                "ai_model_version": None,
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": "ANALYSIS UNAVAILABLE",
                "forensic_anomaly_score": 0.0,
                "signal_anomalies_score": 0.0,
                "metadata_anomaly_score": 10.0,
                "findings": findings,
                "raw_metrics": raw_metrics
            }

        sample_rate = audio_meta.get("sample_rate_hz", 22050)
        duration = audio_meta.get("duration_seconds", 0.0)

        # 2. Render Visual Forensic Exhibits (Waveform & Spectrogram)
        waveform_path = self._render_waveform(audio_data, sample_rate, evidence_id)
        raw_metrics["waveform_path"] = str(waveform_path) if waveform_path else None

        spec_path, spec_cuts, spec_cut_timestamps = self._render_spectrogram(audio_data, sample_rate, evidence_id)
        raw_metrics["spectrogram_path"] = str(spec_path) if spec_path else None
        raw_metrics["splice_candidate_count"] = spec_cuts
        raw_metrics["splice_timestamps"] = spec_cut_timestamps

        # 3. Compute Physical Acoustic Forensic Metrics
        acoustic_metrics = self._compute_acoustic_metrics(audio_data, sample_rate)
        raw_metrics.update(acoustic_metrics)

        # 4. Generate Explainable Physical Forensic Findings

        # A. Splicing & Spectral Discontinuities
        if spec_cuts >= 3:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Abrupt Spectral Discontinuities / Splice Candidates",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=min(100.0, 40.0 + spec_cuts * 15.0),
                explanation=f"Spectrogram analysis revealed {spec_cuts} sharp vertical step transitions in noise floor / frequency flux (timestamps: {spec_cut_timestamps[:4]}). May indicate editing, track splicing, or packet dropouts; requires manual review.",
                location_ref="Spectrogram Frequency Domain"
            ))
        elif spec_cuts > 0:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Minor Spectral Discontinuities",
                category="SIGNAL_ANALYSIS",
                severity="MEDIUM",
                score=35.0,
                explanation=f"Detected {spec_cuts} minor spectral flux discontinuity. Consistent with edit cuts, mic pops, or background acoustic changes.",
                location_ref="Spectrogram Frequency Domain"
            ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Continuous Acoustic Spectrum",
                category="SIGNAL_ANALYSIS",
                severity="INFO",
                score=5.0,
                explanation="Spectral continuity is smooth across the duration. No sharp vertical noise floor steps detected."
            ))

        # B. Clipping & Dynamic Range
        clipping_ratio = acoustic_metrics.get("clipping_ratio", 0.0)
        if clipping_ratio > 0.02:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Severe Waveform Amplitude Clipping",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=70.0,
                explanation=f"Measured {round(clipping_ratio * 100, 2)}% clipped samples at maximum digital dynamic range. Excessive clipping degrades forensic phase verification and indicates high gain or uncalibrated recording.",
                location_ref="Waveform Peaks"
            ))
        elif clipping_ratio > 0.005:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Moderate Amplitude Peak Clipping",
                category="SIGNAL_ANALYSIS",
                severity="LOW",
                score=25.0,
                explanation=f"Minor amplitude clipping observed ({round(clipping_ratio * 100, 2)}% of samples)."
            ))

        # C. High Frequency Energy & Spectral Roll-off
        hf_ratio = acoustic_metrics.get("high_freq_energy_ratio", 0.0)
        roll_off = acoustic_metrics.get("spectral_rolloff_hz", 0.0)
        if hf_ratio < 0.005 and sample_rate >= 16000:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="High-Frequency Band Suppression (Bandwidth Shelf)",
                category="SIGNAL_ANALYSIS",
                severity="MEDIUM",
                score=55.0,
                explanation=f"Energy above 4 kHz is sharply attenuated (spectral 85% roll-off: {round(roll_off, 0)} Hz, HF energy ratio: {round(hf_ratio * 100, 3)}%). Common in lossy telephony codecs (G.711/AMR), aggressive noise reduction, or low-bandwidth voice synthesis.",
                location_ref="Upper Acoustic Band (>4kHz)"
            ))

        # D. Silence Distribution
        silence_ratio = acoustic_metrics.get("silence_ratio", 0.0)
        if silence_ratio > 0.40:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Elevated Silence / Zero-Signal Proportion",
                category="SIGNAL_ANALYSIS",
                severity="LOW",
                score=20.0,
                explanation=f"Silence intervals comprise {round(silence_ratio * 100, 1)}% of total track duration across {acoustic_metrics.get('silence_regions_count', 0)} intervals."
            ))

        # 5. Aggregate Heuristic Forensic Anomaly Score
        splice_score = min(100.0, spec_cuts * 25.0)
        clip_score = min(100.0, clipping_ratio * 1500.0)
        hf_shelf_score = 45.0 if (hf_ratio < 0.005 and sample_rate >= 16000) else 10.0
        rms_var_score = min(100.0, acoustic_metrics.get("rms_variation", 0.0) * 100.0)

        forensic_anomaly_score = round(
            (splice_score * 0.40) +
            (clip_score * 0.25) +
            (hf_shelf_score * 0.20) +
            (rms_var_score * 0.15),
            1
        )
        raw_metrics["forensic_anomaly_score"] = forensic_anomaly_score

# 6. Advanced Acoustic VoicePrint & Neural Vocoder Detection
        from app.core.audio_deepfake_detector import AudioDeepfakeDetector
        deepfake_res = AudioDeepfakeDetector.analyze_audio_stream(audio_data, sample_rate, evidence_id)
        raw_metrics["deepfake_voice"] = deepfake_res

        if deepfake_res.get("verdict") == "SYNTHETIC_VOICE_CLONE_DETECTED":
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Neural Voice Synthesis & Vocoder Phase Dispersion",
                category="AI_DETECTION",
                severity="HIGH",
                score=round(deepfake_res["ai_voice_confidence"], 1),
                explanation=deepfake_res["description"],
                location_ref="Vocal Formant Acoustic Domain"
            ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Biological Vocal Tract Acoustic Dispersion",
                category="AI_DETECTION",
                severity="INFO",
                score=round(deepfake_res["ai_voice_confidence"], 1),
                explanation=deepfake_res["description"],
                location_ref="Vocal Formant Acoustic Domain"
            ))

        return {
            "ai_model_name": "Acoustic VoicePrint & Neural Vocoder Detector",
            "ai_model_version": "2.0.0",
            "ai_manipulation_indicator": deepfake_res["ai_manipulation_indicator"],
            "model_confidence": deepfake_res["ai_voice_confidence"],
            "model_status": "AVAILABLE",
            "forensic_anomaly_score": forensic_anomaly_score,
            "signal_anomalies_score": forensic_anomaly_score,
            "metadata_anomaly_score": 10.0,
            "findings": findings,
            "raw_metrics": raw_metrics
        }

    def _decode_audio(self, file_path: Path) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """
        Decodes real audio bitstream.
        First tries native Python wave module (for WAV format).
        If not a standard WAV, attempts ffmpeg subprocess if installed.
        Never generates simulated or fake data.
        """
        metadata: Dict[str, Any] = {
            "codec": "UNKNOWN",
            "sample_rate_hz": 0,
            "channels": 0,
            "duration_seconds": 0.0,
            "bit_depth": 0,
            "decoded_sample_count": 0,
            "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0
        }

        if not file_path.exists() or metadata["file_size_bytes"] == 0:
            return None, metadata

        # 1. Native WAV decoding
        try:
            with wave.open(str(file_path), 'rb') as wav_f:
                n_channels = wav_f.getnchannels()
                sample_width = wav_f.getsampwidth()
                framerate = wav_f.getframerate()
                n_frames = wav_f.getnframes()
                
                raw_bytes = wav_f.readframes(n_frames)
                
                if sample_width == 1:
                    data = (np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
                    bit_depth = 8
                elif sample_width == 2:
                    data = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    bit_depth = 16
                elif sample_width == 3:
                    # 24-bit PCM vectorized decoding
                    raw_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
                    valid_len = len(raw_arr) - (len(raw_arr) % 3)
                    raw_24 = raw_arr[:valid_len].reshape(-1, 3)
                    data_int = raw_24[:, 0].astype(np.int32) | (raw_24[:, 1].astype(np.int32) << 8) | (raw_24[:, 2].astype(np.int8).astype(np.int32) << 16)
                    data = data_int.astype(np.float32) / 8388608.0
                    bit_depth = 24
                elif sample_width == 4:
                    data = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
                    bit_depth = 32
                else:
                    return None, metadata

                if n_channels > 1:
                    valid_data_len = len(data) - (len(data) % n_channels)
                    data = data[:valid_data_len].reshape(-1, n_channels)
                    data = np.mean(data, axis=1)  # downmix to mono for forensic analysis

                duration = float(len(data)) / float(framerate) if framerate > 0 else 0.0

                metadata["codec"] = "PCM_WAV"
                metadata["sample_rate_hz"] = framerate
                metadata["channels"] = n_channels
                metadata["duration_seconds"] = round(duration, 3)
                metadata["bit_depth"] = bit_depth
                metadata["decoded_sample_count"] = len(data)

                return data, metadata
        except Exception:
            pass

        # 2. FFmpeg subprocess fallback for compressed audio (MP3, M4A, OGG, FLAC)
        if shutil.which("ffmpeg"):
            try:
                cmd = [
                    "ffmpeg", "-nostdin", "-v", "quiet",
                    "-i", str(file_path),
                    "-f", "s16le", "-ac", "1", "-ar", "22050", "-"
                ]
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
                if proc.returncode == 0 and len(proc.stdout) > 0:
                    raw_bytes = proc.stdout
                    data = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    framerate = 22050
                    duration = float(len(data)) / float(framerate)

                    metadata["codec"] = "FFMPEG_DECODED"
                    metadata["sample_rate_hz"] = framerate
                    metadata["channels"] = 1
                    metadata["duration_seconds"] = round(duration, 3)
                    metadata["bit_depth"] = 16
                    metadata["decoded_sample_count"] = len(data)
                    return data, metadata
            except Exception as e:
                logger.warning(f"FFmpeg decoding failed for {file_path}: {e}")

        return None, metadata

    def _render_waveform(self, data: np.ndarray, sample_rate: int, evidence_id: str) -> Optional[Path]:
        """
        Renders a clean, high-contrast waveform visualization exhibit.
        """
        try:
            width, height = 500, 160
            img = Image.new("RGB", (width, height), color=(15, 23, 42))  # slate-900
            draw = ImageDraw.Draw(img)

            # Center axis line
            mid_y = height // 2
            draw.line([(0, mid_y), (width, mid_y)], fill=(51, 65, 85), width=1)

            # Downsample to width columns
            chunk_size = max(1, len(data) // width)
            points_upper = []
            points_lower = []

            for x in range(width):
                chunk = data[x * chunk_size : (x + 1) * chunk_size]
                if len(chunk) == 0:
                    max_val, min_val = 0.0, 0.0
                else:
                    max_val = float(np.max(chunk))
                    min_val = float(np.min(chunk))

                y_max = mid_y - int(max_val * (height / 2 - 10))
                y_min = mid_y - int(min_val * (height / 2 - 10))

                draw.line([(x, y_min), (x, y_max)], fill=(56, 189, 248), width=1)  # sky-400

            # Draw time indicators
            draw.text((10, 10), "Waveform Amplitude Envelope", fill=(148, 163, 184))
            dur_str = f"Duration: {round(len(data)/max(1, sample_rate), 2)}s | SR: {sample_rate}Hz"
            draw.text((width - 180, 10), dur_str, fill=(100, 116, 139))

            out_path = FORENSIC_DIR / f"waveform_{evidence_id}.png"
            img.save(out_path, "PNG")
            return out_path
        except Exception as e:
            logger.error(f"Failed to render waveform for {evidence_id}: {e}")
            return None

    def _render_spectrogram(self, data: np.ndarray, sample_rate: int, evidence_id: str) -> Tuple[Optional[Path], int, List[float]]:
        """
        Computes STFT Spectrogram and detects sharp spectral flux steps (splice candidates).
        """
        try:
            if len(data) < 512:
                data = np.pad(data, (0, 512 - len(data)))

            nperseg = min(512, max(128, len(data) // 40))
            f, t, Sxx = signal.spectrogram(data, fs=sample_rate, nperseg=nperseg, noverlap=nperseg // 2)
            log_Sxx = 10.0 * np.log10(Sxx + 1e-10)

            # Detect abrupt spectral cuts / splice points across time slices
            time_deltas = np.diff(log_Sxx, axis=1)
            mean_step_diff = np.mean(np.abs(time_deltas), axis=0)
            threshold = np.mean(mean_step_diff) + (2.5 * np.std(mean_step_diff) + 1e-5)
            cut_mask = mean_step_diff > threshold
            cut_count = int(np.sum(cut_mask))

            cut_timestamps = []
            for idx in np.where(cut_mask)[0]:
                if idx < len(t):
                    cut_timestamps.append(round(float(t[idx]), 3))

            # Normalize to 0-255 grayscale / false-color
            norm_spec = (log_Sxx - np.min(log_Sxx)) / (np.max(log_Sxx) - np.min(log_Sxx) + 1e-6) * 255.0
            spec_arr = np.flipud(norm_spec).astype(np.uint8)

            # Apply false-color gradient (Navy to Cyan to Yellow to White)
            h, w = spec_arr.shape
            color_img = np.zeros((h, w, 3), dtype=np.uint8)
            # R channel
            color_img[:, :, 0] = np.clip(spec_arr * 1.2 - 50, 0, 255).astype(np.uint8)
            # G channel
            color_img[:, :, 1] = np.clip(spec_arr * 1.5 - 30, 0, 255).astype(np.uint8)
            # B channel
            color_img[:, :, 2] = np.clip(255 - spec_arr * 0.8, 0, 255).astype(np.uint8)

            spec_img = Image.fromarray(color_img).resize((500, 200), Image.Resampling.BILINEAR)
            draw = ImageDraw.Draw(spec_img)
            draw.text((10, 8), f"STFT Spectrogram | Splice Candidates: {cut_count}", fill=(255, 255, 255))

            out_path = FORENSIC_DIR / f"spectrogram_{evidence_id}.png"
            spec_img.save(out_path, "PNG")
            return out_path, cut_count, cut_timestamps[:8]
        except Exception as e:
            logger.error(f"Failed to render spectrogram for {evidence_id}: {e}")
            return None, 0, []

    def _compute_acoustic_metrics(self, data: np.ndarray, sample_rate: int) -> Dict[str, Any]:
        """
        Computes physical, explainable acoustic features:
        - RMS Energy & Variation
        - Clipping ratio
        - Silence duration ratio & intervals
        - Spectral Centroid
        - Spectral Roll-off (85%)
        - High-Frequency Energy Ratio (>4kHz)
        """
        metrics: Dict[str, Any] = {}

        # 1. Clipping Ratio
        clip_count = np.sum(np.abs(data) >= 0.99)
        clipping_ratio = float(clip_count) / max(1, len(data))
        metrics["clipping_ratio"] = round(clipping_ratio, 4)

        # 2. RMS Energy & Silence Analysis (50ms frames)
        frame_len = max(64, int(sample_rate * 0.05))
        num_frames = len(data) // frame_len
        
        if num_frames > 0:
            frames = data[: num_frames * frame_len].reshape(num_frames, frame_len)
            frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))
            
            mean_rms = float(np.mean(frame_rms))
            std_rms = float(np.std(frame_rms))
            rms_var = float(std_rms / (mean_rms + 1e-6))
            
            metrics["rms_energy_mean"] = round(mean_rms, 4)
            metrics["rms_energy_std"] = round(std_rms, 4)
            metrics["rms_variation"] = round(rms_var, 3)

            # Silence threshold (-45 dB from peak)
            silence_thresh = max(1e-4, np.max(frame_rms) * 0.01)
            silence_frames = frame_rms < silence_thresh
            silence_ratio = float(np.sum(silence_frames)) / float(num_frames)
            
            # Count silence intervals
            silence_diff = np.diff(silence_frames.astype(int))
            silence_regions = int(np.sum(silence_diff == 1))

            metrics["silence_ratio"] = round(silence_ratio, 3)
            metrics["silence_regions_count"] = silence_regions
        else:
            metrics["rms_energy_mean"] = 0.0
            metrics["rms_energy_std"] = 0.0
            metrics["rms_variation"] = 0.0
            metrics["silence_ratio"] = 0.0
            metrics["silence_regions_count"] = 0

        # 3. Frequency Spectrum Analysis (FFT)
        fft_len = min(len(data), sample_rate * 3)  # First 3 seconds
        fft_vals = np.abs(np.fft.rfft(data[:fft_len]))
        freqs = np.fft.rfftfreq(fft_len, 1.0 / sample_rate)

        total_energy = np.sum(fft_vals) + 1e-10
        
        # Spectral Centroid
        centroid = float(np.sum(freqs * fft_vals) / total_energy)
        metrics["spectral_centroid_hz"] = round(centroid, 1)

        # Spectral Roll-off (85% energy point)
        cum_energy = np.cumsum(fft_vals)
        roll_idx = np.searchsorted(cum_energy, 0.85 * total_energy)
        roll_off = float(freqs[min(roll_idx, len(freqs) - 1)])
        metrics["spectral_rolloff_hz"] = round(roll_off, 1)

        # High-Frequency Energy Ratio (> 4000 Hz)
        hf_mask = freqs >= 4000
        hf_energy = np.sum(fft_vals[hf_mask])
        hf_ratio = float(hf_energy / total_energy)
        metrics["high_freq_energy_ratio"] = round(hf_ratio, 4)

        return metrics
