import os
import math
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
from PIL import Image

from app.analyzers.base_analyzer import BaseAnalyzer
from app.analyzers.hf_image_detector import HFImageDetector
from app.core.explainability import FindingBuilder
from app.config import FORENSIC_DIR

logger = logging.getLogger(__name__)

class VideoAnalyzer(BaseAnalyzer):
    """
    Forensic Video Analyzer.
    Combines:
    1. Real Frame Decoding & Temporal Heuristics: Evaluates container metadata,
       temporal luminance variation, and inter-frame pixel differences.
    2. Local Hugging Face ML Vision Classifier (Frame-Level Aggregation):
       Runs 'dima806/deepfake_vs_real_image_detection' across uniformly sampled
       real decoded frames (max 16) and computes median AI manipulation indicator.
    """

    def __init__(self):
        self.hf_detector = HFImageDetector()
        self.max_sampled_frames = 16

    def analyze(self, file_path: Path, evidence_id: str) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        raw_metrics: Dict[str, Any] = {}

        # 1. Container & Atom Inspection
        container_info, meta_score = self._inspect_container(file_path, evidence_id, findings)
        raw_metrics["container"] = container_info

        # 2. Real Video Frame Decoding & Sampling
        decoded_frames, frame_metadata = self._decode_and_sample_frames(file_path)
        raw_metrics.update(frame_metadata)

        sampled_count = len(decoded_frames)
        raw_metrics["sampled_frames_count"] = sampled_count

        if sampled_count > 0:
            try:
                saved_frames_info = []
                max_saved = min(4, sampled_count)
                save_indices = [int(i * (sampled_count - 1) / max(1, max_saved - 1)) for i in range(max_saved)] if max_saved > 1 else [0]
                for rank, idx in enumerate(save_indices):
                    frame_img = decoded_frames[idx]
                    f_name = f"video_frame_{evidence_id}_{rank}.jpg"
                    f_path = FORENSIC_DIR / f_name
                    frame_img.save(f_path, "JPEG", quality=85)
                    ts = frame_metadata.get("frame_timestamps", [])
                    t_val = ts[idx] if idx < len(ts) else 0.0
                    saved_frames_info.append({
                        "frame_index": idx,
                        "rank": rank,
                        "timestamp_sec": round(t_val, 2),
                        "artifact_name": f_name
                    })

                mid_idx = sampled_count // 2
                primary_path = FORENSIC_DIR / f"video_frame_{evidence_id}.jpg"
                decoded_frames[mid_idx].save(primary_path, "JPEG", quality=85)
                raw_metrics["video_frame_path"] = str(primary_path)
                raw_metrics["saved_sample_frames"] = saved_frames_info
            except Exception as e:
                logger.warning(f"Failed to save video keyframe exhibits: {e}")

        # If no frames could be decoded, return ANALYSIS UNAVAILABLE with zero made-up scores
        if sampled_count == 0:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Video Frame Decoding: ANALYSIS UNAVAILABLE",
                category="SIGNAL_ANALYSIS",
                severity="MEDIUM",
                score=50.0,
                explanation="Video decoder was unable to extract valid visual frames from container (corrupted stream, unsupported codec, or empty payload).",
                location_ref="Video Stream"
            ))
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Video ViT Frame Analysis: ANALYSIS UNAVAILABLE",
                category="AI_DETECTION",
                severity="MEDIUM",
                score=50.0,
                explanation="No decoded video frames were available for local ViT vision model evaluation.",
                location_ref="Local Inference Engine"
            ))
            return {
                "ai_model_name": self.hf_detector.model_name,
                "ai_model_version": self.hf_detector.model_revision,
                "ai_manipulation_indicator": None,
                "model_confidence": None,
                "model_status": "ANALYSIS UNAVAILABLE",
                "forensic_anomaly_score": 0.0,
                "signal_anomalies_score": 0.0,
                "metadata_anomaly_score": meta_score,
                "findings": findings,
                "raw_metrics": raw_metrics
            }

        # -------------------------------------------------------------
        # 3. HEURISTIC TEMPORAL FORENSIC SIGNALS
        # -------------------------------------------------------------
        temporal_metrics, temporal_finding = self._analyze_temporal_heuristics(decoded_frames, evidence_id)
        raw_metrics.update(temporal_metrics)
        findings.append(temporal_finding)

        flicker_score = temporal_metrics.get("temporal_luminance_variation_score", 10.0)
        inter_frame_score = temporal_metrics.get("inter_frame_inconsistency_score", 10.0)
        forensic_anomaly_score = round((flicker_score * 0.60) + (inter_frame_score * 0.40), 1)
        raw_metrics["forensic_anomaly_score"] = forensic_anomaly_score

        # -------------------------------------------------------------
        # 4. LOCAL HUGGING FACE FRAME-LEVEL ML INFERENCE & AGGREGATION
        # -------------------------------------------------------------
        ml_aggregation = self._run_ml_frame_aggregation(decoded_frames, frame_metadata.get("frame_timestamps", []))
        raw_metrics["ml_detector"] = ml_aggregation

        model_status = ml_aggregation["model_status"]
        ai_indicator = ml_aggregation["ai_manipulation_indicator"]
        model_conf = ml_aggregation["model_confidence"]
        analysed_count = ml_aggregation["analysed_frame_count"]
        iqr_val = ml_aggregation.get("iqr_ai_indicator")
        model_name = self.hf_detector.model_name
        model_ver = self.hf_detector.model_revision

        # ML Finding Generation
        if model_status == "AVAILABLE" and ai_indicator is not None:
            pct_val = round(ai_indicator * 100, 1)
            conf_pct = round(model_conf * 100, 1) if model_conf else 0
            iqr_pct = round(iqr_val * 100, 1) if iqr_val is not None else 0
            
            if ai_indicator >= 0.70:
                findings.append(FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name=f"Video Frame ViT Aggregate Flag ({model_name})",
                    category="AI_DETECTION",
                    severity="CRITICAL" if ai_indicator > 0.85 else "HIGH",
                    score=pct_val,
                    explanation=f"Local Vision Transformer evaluated {analysed_count}/{sampled_count} decoded frames, yielding a median AI manipulation indicator of {pct_val}% (IQR dispersion: {iqr_pct}%, confidence: {conf_pct}%). Note: Automated statistical signal, not definitive proof of video manipulation.",
                    location_ref="Decoded Keyframe Sequence"
                ))
            elif ai_indicator >= 0.35:
                findings.append(FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name=f"Video Frame ViT Aggregate Intermediate ({model_name})",
                    category="AI_DETECTION",
                    severity="MEDIUM",
                    score=pct_val,
                    explanation=f"Local Vision Transformer evaluated {analysed_count}/{sampled_count} decoded frames with an intermediate median AI manipulation indicator of {pct_val}% (IQR dispersion: {iqr_pct}%, confidence: {conf_pct}%). Requires manual forensic review.",
                    location_ref="Decoded Keyframe Sequence"
                ))
            else:
                findings.append(FindingBuilder.create_finding(
                    evidence_id=evidence_id,
                    signal_name=f"Video Frame ViT Aggregate Baseline ({model_name})",
                    category="AI_DETECTION",
                    severity="INFO",
                    score=pct_val,
                    explanation=f"Local Vision Transformer evaluated {analysed_count}/{sampled_count} decoded frames indicating low probability of manipulation across sampled keyframes (median: {pct_val}%, confidence: {conf_pct}%)."
                ))
        elif model_status == "ANALYSIS INCONCLUSIVE":
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name=f"Video ViT Frame Analysis: ANALYSIS INCONCLUSIVE",
                category="AI_DETECTION",
                severity="MEDIUM",
                score=50.0,
                explanation=f"Video ViT frame analysis was inconclusive ({ml_aggregation.get('error_detail', 'Fewer than 3 frames produced valid model outputs')}). Statistical indicator is withheld.",
                location_ref="Decoded Keyframe Sequence"
            ))
        else:
            findings.append(FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name=f"Video ViT Frame Analysis: ANALYSIS UNAVAILABLE",
                category="AI_DETECTION",
                severity="MEDIUM",
                score=50.0,
                explanation=f"Local Hugging Face vision model '{model_name}' was unavailable for frame inference ({ml_aggregation.get('error_detail', 'Inference offline')}). Video assessment is grounded exclusively on physical temporal and container signals.",
                location_ref="Local Inference Engine"
            ))

        return {
            "ai_model_name": model_name,
            "ai_model_version": model_ver,
            "ai_manipulation_indicator": ai_indicator,
            "model_confidence": model_conf,
            "model_status": model_status,
            "forensic_anomaly_score": forensic_anomaly_score,
            "signal_anomalies_score": forensic_anomaly_score,
            "metadata_anomaly_score": meta_score,
            "findings": findings,
            "raw_metrics": raw_metrics
        }

    def _inspect_container(self, file_path: Path, evidence_id: str, findings: List[Dict[str, Any]]) -> (Dict[str, Any], float):
        size_bytes = file_path.stat().st_size if file_path.exists() else 0
        info = {
            "size_bytes": size_bytes,
            "has_moov": False,
            "has_ftyp": False,
            "encoder": "Unknown"
        }
        meta_score = 0.0

        if not file_path.exists() or size_bytes == 0:
            return info, meta_score

        try:
            with open(file_path, "rb") as f:
                if size_bytes <= 1024 * 1024:
                    container_bytes = f.read()
                else:
                    header = f.read(512 * 1024)
                    f.seek(size_bytes - 512 * 1024)
                    trailer = f.read(512 * 1024)
                    container_bytes = header + trailer
            
            if b"ftyp" in container_bytes:
                info["has_ftyp"] = True
            if b"moov" in container_bytes or b"mdat" in container_bytes:
                info["has_moov"] = True
            
            generative_tags = ["DeepFaceLab", "Sora", "Runway", "Pika", "Kling", "Luma", "Hailuo", "AnimateDiff", "Stable Video"]
            for sw in [b"Adobe Premiere", b"CapCut", b"DaVinci Resolve", b"InShot", b"ffmpeg", b"HandBrake", b"DeepFaceLab", b"Sora", b"Runway", b"Pika", b"Kling", b"Luma", b"Hailuo", b"AnimateDiff", b"Stable Video"]:
                if sw.lower() in container_bytes.lower():
                    sw_name = sw.decode(errors='ignore')
                    info["encoder"] = sw_name
                    if sw_name in generative_tags:
                        meta_score = 95.0
                        findings.append(FindingBuilder.create_finding(
                            evidence_id=evidence_id,
                            signal_name="Generative Video AI Pipeline Tag Detected",
                            category="METADATA",
                            severity="CRITICAL",
                            score=98.0,
                            explanation=f"Video metadata atom explicitly references '{sw_name}' neural generation pipeline."
                        ))
                    else:
                        meta_score = 40.0
                        findings.append(FindingBuilder.create_finding(
                            evidence_id=evidence_id,
                            signal_name="Video Editor Software Atom Found",
                            category="METADATA",
                            severity="MEDIUM",
                            score=50.0,
                            explanation=f"Video container contains encoder tags from editing suite: '{sw_name}'."
                        ))
                    break
        except Exception:
            pass

        return info, meta_score

    def _decode_and_sample_frames(self, file_path: Path) -> (List[Image.Image], Dict[str, Any]):
        """
        Decodes real video frames using OpenCV with uniform sampling up to max 16 frames.
        Never fabricates or simulates frames.
        """
        frames: List[Image.Image] = []
        metadata: Dict[str, Any] = {
            "total_frames_in_stream": 0,
            "fps": 0.0,
            "duration_seconds": 0.0,
            "sampled_frame_indices": [],
            "frame_timestamps": [],
            "video_resolution": None
        }

        if not file_path.exists():
            return [], metadata

        try:
            import cv2
            cap = cv2.VideoCapture(str(file_path))
            if not cap.isOpened():
                return [], metadata

            try:
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = float(cap.get(cv2.CAP_PROP_FPS))
                if not fps or math.isnan(fps) or fps <= 0 or fps > 240:
                    fps = 25.0

                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                if width > 0 and height > 0:
                    metadata["video_resolution"] = f"{width}x{height}"

                metadata["total_frames_in_stream"] = total_frames
                metadata["fps"] = round(fps, 2)
                metadata["duration_seconds"] = round(total_frames / fps, 2) if total_frames > 0 else 0.0

                if total_frames <= 0:
                    # Attempt sequential read if frame count is unindexed
                    seq_frames = []
                    count = 0
                    while count < self.max_sampled_frames:
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            break
                        if frame.ndim == 2 or (frame.ndim == 3 and frame.shape[2] == 1):
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
                        elif frame.ndim == 3 and frame.shape[2] == 4:
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
                        elif frame.ndim == 3 and frame.shape[2] == 3:
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        else:
                            continue
                        seq_frames.append(Image.fromarray(rgb_frame))
                        metadata["sampled_frame_indices"].append(count)
                        metadata["frame_timestamps"].append(round(count / fps, 3))
                        count += 1
                    return seq_frames, metadata

                # Calculate uniform sampling indices
                sample_count = min(self.max_sampled_frames, total_frames)
                if sample_count <= 0:
                    return [], metadata

                indices = np.linspace(0, total_frames - 1, num=sample_count, dtype=int)
                indices = sorted(list(set(indices.tolist())))

                for idx in indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        if frame.ndim == 2 or (frame.ndim == 3 and frame.shape[2] == 1):
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
                        elif frame.ndim == 3 and frame.shape[2] == 4:
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
                        elif frame.ndim == 3 and frame.shape[2] == 3:
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        else:
                            continue
                        frames.append(Image.fromarray(rgb_frame))
                        metadata["sampled_frame_indices"].append(int(idx))
                        metadata["frame_timestamps"].append(round(float(idx) / fps, 3))

                return frames, metadata
            finally:
                cap.release()
        except Exception as e:
            logger.error(f"Error decoding video frames from {file_path}: {e}")
            return [], metadata

    def _analyze_temporal_heuristics(self, frames: List[Image.Image], evidence_id: str) -> (Dict[str, Any], Dict[str, Any]):
        """
        Computes temporal luminance variation and inter-frame difference across real frames.
        """
        if len(frames) < 2:
            return {
                "temporal_luminance_variation_score": 10.0,
                "inter_frame_inconsistency_score": 10.0
            }, FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Single Keyframe Available",
                category="SIGNAL_ANALYSIS",
                severity="INFO",
                score=10.0,
                explanation="Video contains fewer than 2 decoded frames for temporal variance calculation."
            )

        gray_arrays = [np.array(f.convert("L").resize((256, 256), Image.Resampling.BILINEAR), dtype=np.float32) for f in frames]

        # 1. Temporal Luminance Variation
        means = [float(np.mean(arr)) for arr in gray_arrays]
        diffs = np.abs(np.diff(means))
        flicker_val = float(np.mean(diffs) / (np.std(means) + 1e-6))
        luminance_variation_score = round(min(100.0, max(5.0, flicker_val * 35.0)), 1)

        # 2. Inter-Frame Difference Inconsistency
        frame_diffs = []
        for i in range(len(gray_arrays) - 1):
            d = float(np.mean(np.abs(gray_arrays[i] - gray_arrays[i+1])))
            frame_diffs.append(d)
        
        if len(frame_diffs) > 1:
            inter_inconsistency = round(min(100.0, max(5.0, float(np.std(frame_diffs)) * 3.0)), 1)
        elif len(frame_diffs) == 1:
            inter_inconsistency = round(min(100.0, max(5.0, frame_diffs[0] * 1.5)), 1)
        else:
            inter_inconsistency = 10.0

        metrics = {
            "temporal_luminance_variation_score": luminance_variation_score,
            "inter_frame_inconsistency_score": inter_inconsistency,
            "mean_inter_frame_diff": round(float(np.mean(frame_diffs)), 2)
        }

        if luminance_variation_score > 60.0:
            finding = FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="High Temporal Luminance Variation",
                category="SIGNAL_ANALYSIS",
                severity="HIGH",
                score=luminance_variation_score,
                explanation=f"Measured elevated frame-to-frame luminance variation (score: {luminance_variation_score}/100) across {len(frames)} sampled frames. Note: Automated physical signal, not proof of video manipulation.",
                location_ref="Sampled Frame Sequence"
            )
        else:
            finding = FindingBuilder.create_finding(
                evidence_id=evidence_id,
                signal_name="Consistent Temporal Frame Dynamics",
                category="SIGNAL_ANALYSIS",
                severity="INFO",
                score=luminance_variation_score,
                explanation=f"Sampled {len(frames)} keyframes exhibit smooth temporal luminance continuity."
            )

        return metrics, finding

    def _run_ml_frame_aggregation(self, frames: List[Image.Image], timestamps: List[float]) -> Dict[str, Any]:
        """
        Evaluates each decoded frame using HFImageDetector and aggregates valid outputs via median.
        """
        valid_indicators: List[float] = []
        valid_confidences: List[float] = []
        frame_results: List[Dict[str, Any]] = []
        unavailable_count = 0
        inconclusive_count = 0

        for i, frame_img in enumerate(frames):
            ts = timestamps[i] if i < len(timestamps) else 0.0
            res = self.hf_detector.predict(frame_img)
            status = res["model_status"]
            ind = res.get("ai_manipulation_indicator")
            conf = res.get("model_confidence")

            frame_entry = {
                "frame_index": i,
                "timestamp_seconds": ts,
                "model_status": status,
                "ai_manipulation_indicator": ind,
                "model_confidence": conf
            }
            frame_results.append(frame_entry)

            if status == "AVAILABLE" and ind is not None:
                valid_indicators.append(ind)
                if conf is not None:
                    valid_confidences.append(conf)
            elif status == "ANALYSIS INCONCLUSIVE":
                inconclusive_count += 1
            else:
                unavailable_count += 1

        analysed_count = len(valid_indicators)

        # Require at least 3 valid frame results for statistical validity
        if analysed_count < 3:
            if len(frames) < 3:
                overall_status = "ANALYSIS INCONCLUSIVE"
                err = f"Video contains only {len(frames)} decoded frame(s); minimum 3 required for statistical frame aggregation."
            elif unavailable_count > inconclusive_count:
                overall_status = "ANALYSIS UNAVAILABLE"
                err = f"Local ML vision model was unavailable on {unavailable_count}/{len(frames)} decoded frames."
            else:
                overall_status = "ANALYSIS INCONCLUSIVE"
                err = f"Model yielded inconclusive class mappings on {inconclusive_count}/{len(frames)} decoded frames."

            return {
                "model_status": overall_status,
                "ai_manipulation_indicator": None,
                "model_confidence": round(float(np.mean(valid_confidences)), 4) if valid_confidences else None,
                "sampled_frame_count": len(frames),
                "analysed_frame_count": analysed_count,
                "unavailable_frame_count": unavailable_count,
                "inconclusive_frame_count": inconclusive_count,
                "median_ai_indicator": None,
                "iqr_ai_indicator": None,
                "frame_details": frame_results,
                "error_detail": err
            }

        # Compute Median and IQR
        median_val = float(np.median(valid_indicators))
        q75, q25 = np.percentile(valid_indicators, [75, 25])
        iqr_val = float(q75 - q25)
        median_conf = float(np.median(valid_confidences)) if valid_confidences else 0.90

        return {
            "model_status": "AVAILABLE",
            "ai_manipulation_indicator": round(median_val, 4),
            "model_confidence": round(median_conf, 4),
            "sampled_frame_count": len(frames),
            "analysed_frame_count": analysed_count,
            "unavailable_frame_count": unavailable_count,
            "inconclusive_frame_count": inconclusive_count,
            "median_ai_indicator": round(median_val, 4),
            "iqr_ai_indicator": round(iqr_val, 4),
            "frame_details": frame_results,
            "error_detail": None
        }
