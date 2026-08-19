from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List

class BaseAnalyzer(ABC):
    """
    Abstract base class for all forensic modality analyzers.
    """

    @abstractmethod
    def analyze(self, file_path: Path, evidence_id: str) -> Dict[str, Any]:
        """
        Executes modality-specific forensic signal extraction.
        
        Returns:
            Dict containing:
                - 'ai_manipulation_score': float (0.0 to 1.0)
                - 'ai_model_name': str
                - 'signal_anomalies_score': float (0.0 to 100.0)
                - 'metadata_anomaly_score': float (0.0 to 100.0)
                - 'findings': List[Dict[str, Any]]
                - 'raw_metrics': Dict[str, Any]
        """
        pass
