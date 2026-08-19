import uuid
from datetime import datetime
from typing import List, Dict, Any
from app.database import get_db

class ChainOfCustodyLogger:
    """
    Manages the append-only application custody log designed to support forensic
    workflow documentation. Stored in local SQLite; not an independent cryptographic
    proof or a replacement for formal evidence-management procedures.
    """

    @staticmethod
    def record_event(
        evidence_id: str,
        action: str,
        actor: str,
        recorded_sha256: str,
        details: str
    ) -> Dict[str, Any]:
        event_id = f"COC-{uuid.uuid4().hex[:10].upper()}"
        timestamp = datetime.utcnow().isoformat() + "Z"

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO chain_of_custody (event_id, evidence_id, action, actor, recorded_sha256, details, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (event_id, evidence_id, action, actor, recorded_sha256, details, timestamp))

        return {
            "event_id": event_id,
            "evidence_id": evidence_id,
            "action": action,
            "actor": actor,
            "recorded_sha256": recorded_sha256,
            "details": details,
            "timestamp": timestamp
        }

    @staticmethod
    def get_evidence_custody_trail(evidence_id: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM chain_of_custody
            WHERE evidence_id = ?
            ORDER BY timestamp ASC
            """, (evidence_id,))
            return cursor.fetchall()
