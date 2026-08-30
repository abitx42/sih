"""
app/core/consensus_engine.py
=============================
Multi-Signal Cross-Verification Consensus Engine.
Combines local ML ensemble, external API, PRNU, ELA, C2PA, and reverse search
into a unified consensus verdict with conflict detection.
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ConsensusEngine:
    VERSION = "1.0.0"
    
    # Minimum signals required for high-confidence verdict
    MIN_SIGNALS_HIGH_CONFIDENCE = 3
    AGREEMENT_THRESHOLD = 0.65  # Signals above this = "AI detected"
    DISAGREEMENT_THRESHOLD = 0.35  # Signals below this = "Likely authentic"
    
    @classmethod
    def compute_consensus(
        cls,
        signals: Dict[str, Optional[float]],
        evidence_id: str = "EVIDENCE"
    ) -> Dict[str, Any]:
        """
        Computes consensus from multiple detection signals.
        
        signals dict keys:
        - 'hf_ensemble': float 0-1 from local HuggingFace ensemble
        - 'sightengine': float 0-1 from SightEngine external API
        - 'prnu_ai_indicator': float 0-1 from PRNU ballistics
        - 'ela_anomaly': float 0-100 from ELA analysis (normalize to 0-1)
        - 'c2pa_verified': bool or None from C2PA check
        - 'reverse_search_ai_platform': bool from reverse image search
        """
        available_signals = {}
        for key, val in signals.items():
            if val is not None:
                if key == 'ela_anomaly':
                    available_signals[key] = min(1.0, float(val) / 100.0)
                elif key == 'c2pa_verified':
                    available_signals[key] = 0.05 if val else 0.5  # Verified provenance = strong authentic signal
                elif key == 'reverse_search_ai_platform':
                    if val:
                        available_signals[key] = 0.95
                else:
                    available_signals[key] = float(val)
        
        n_signals = len(available_signals)
        
        if n_signals == 0:
            return cls._no_data_result(evidence_id)
        
        values = list(available_signals.values())
        mean_score = sum(values) / len(values)
        
        # Count agreements
        ai_votes = sum(1 for v in values if v >= cls.AGREEMENT_THRESHOLD)
        authentic_votes = sum(1 for v in values if v <= cls.DISAGREEMENT_THRESHOLD)
        ambiguous_votes = n_signals - ai_votes - authentic_votes
        
        # Detect conflicts
        has_conflict = ai_votes > 0 and authentic_votes > 0
        
        # Determine verdict
        if has_conflict:
            verdict = "CONFLICTING_SIGNALS_REVIEW_REQUIRED"
            confidence = "LOW"
        elif ai_votes >= cls.MIN_SIGNALS_HIGH_CONFIDENCE:
            verdict = "CONSENSUS_AI_GENERATED"
            confidence = "HIGH" if ai_votes >= 4 else "MEDIUM"
        elif authentic_votes >= cls.MIN_SIGNALS_HIGH_CONFIDENCE:
            verdict = "CONSENSUS_LIKELY_AUTHENTIC"
            confidence = "HIGH" if authentic_votes >= 4 else "MEDIUM"
        elif mean_score >= 0.6:
            verdict = "LEANING_AI_GENERATED"
            confidence = "LOW"
        elif mean_score <= 0.4:
            verdict = "LEANING_AUTHENTIC"
            confidence = "LOW"
        else:
            verdict = "INCONCLUSIVE_REVIEW_REQUIRED"
            confidence = "LOW"
        
        return {
            "evidence_id": evidence_id,
            "consensus_verdict": verdict,
            "consensus_confidence": confidence,
            "mean_ai_score": round(mean_score, 4),
            "total_signals": n_signals,
            "ai_votes": ai_votes,
            "authentic_votes": authentic_votes,
            "ambiguous_votes": ambiguous_votes,
            "has_conflict": has_conflict,
            "signal_breakdown": {k: round(v, 4) for k, v in available_signals.items()},
            "version": cls.VERSION
        }
    
    @classmethod
    def _no_data_result(cls, evidence_id: str) -> Dict[str, Any]:
        return {
            "evidence_id": evidence_id,
            "consensus_verdict": "NO_SIGNALS_AVAILABLE",
            "consensus_confidence": "NONE",
            "mean_ai_score": None,
            "total_signals": 0,
            "version": cls.VERSION
        }
