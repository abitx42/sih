import uuid
from datetime import datetime
from typing import Dict, Any, List
from app.models.schemas import FindingSchema

class FindingBuilder:
    """
    Standardized constructor for explainable forensic findings.
    """
    @staticmethod
    def create_finding(
        evidence_id: str,
        signal_name: str,
        category: str,
        severity: str,
        score: float,
        explanation: str,
        location_ref: str = None
    ) -> Dict[str, Any]:
        return {
            "finding_id": f"FIND-{uuid.uuid4().hex[:8].upper()}",
            "evidence_id": evidence_id,
            "signal_name": signal_name,
            "category": category,
            "severity": severity.upper(),
            "score": round(float(score), 2),
            "explanation": explanation,
            "location_ref": location_ref,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
