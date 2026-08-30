import hashlib
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.database import get_db


class ChainOfCustodyLogger:
    """
    Manages the append-only application custody log with optional hash-chaining.
    Each new event records a SHA-256 hash of the previous event's key fields,
    making tampering with historical events detectable.
    
    Stored in local SQLite; not an independent cryptographic proof or a replacement
    for formal evidence-management procedures.
    """

    @staticmethod
    def _compute_event_hash(event_id: str, evidence_id: str, action: str, timestamp: str, recorded_sha256: str) -> str:
        """Compute a deterministic SHA-256 hash of this event's identity fields."""
        payload = f"{event_id}|{evidence_id}|{action}|{timestamp}|{recorded_sha256}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _get_latest_event_hash(evidence_id: str) -> str:
        """Retrieve the hash of the most recent custody event for this evidence item."""
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT event_id, evidence_id, action, timestamp, recorded_sha256 "
                    "FROM chain_of_custody WHERE evidence_id = ? ORDER BY timestamp DESC LIMIT 1",
                    (evidence_id,)
                )
                row = cursor.fetchone()
                if row:
                    return ChainOfCustodyLogger._compute_event_hash(
                        row["event_id"], row["evidence_id"], row["action"],
                        row["timestamp"], row["recorded_sha256"]
                    )
        except Exception:
            pass
        return ""  # Genesis event has no previous hash

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
            # Fetch latest event within the same connection to prevent race conditions
            cursor.execute("""
                SELECT event_id, evidence_id, action, timestamp, recorded_sha256
                FROM chain_of_custody
                WHERE evidence_id = ?
                ORDER BY id DESC LIMIT 1
            """, (evidence_id,))
            last_row = cursor.fetchone()
            if last_row:
                previous_event_hash = ChainOfCustodyLogger._compute_event_hash(
                    event_id=last_row["event_id"],
                    evidence_id=last_row["evidence_id"],
                    action=last_row["action"],
                    timestamp=last_row["timestamp"],
                    recorded_sha256=last_row["recorded_sha256"]
                )
            else:
                previous_event_hash = ""

            cursor.execute("""
                INSERT INTO chain_of_custody
                    (event_id, evidence_id, action, actor, recorded_sha256, details, timestamp, previous_event_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, evidence_id, action, actor, recorded_sha256, details, timestamp, previous_event_hash))

        return {
            "event_id": event_id,
            "evidence_id": evidence_id,
            "action": action,
            "actor": actor,
            "recorded_sha256": recorded_sha256,
            "details": details,
            "timestamp": timestamp,
            "previous_event_hash": previous_event_hash
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

    @staticmethod
    def verify_chain(evidence_id: str) -> Dict[str, Any]:
        """
        Walk the custody chain for this evidence item and verify hash linkage.
        Returns dict with chain_valid flag and details of any broken links.
        """
        with get_db() as conn:
            cursor = conn.cursor()
            # Check column exists
            cursor.execute("PRAGMA table_info(chain_of_custody)")
            cols = [c["name"] for c in cursor.fetchall()]
            has_hash_chain = "previous_event_hash" in cols

            cursor.execute(
                "SELECT * FROM chain_of_custody WHERE evidence_id = ? ORDER BY timestamp ASC",
                (evidence_id,)
            )
            events = cursor.fetchall()

        if not events:
            return {"evidence_id": evidence_id, "chain_valid": True, "total_events": 0, "broken_links": [], "status": "CHAIN_EMPTY"}

        if not has_hash_chain:
            return {
                "evidence_id": evidence_id,
                "chain_valid": True,
                "total_events": len(events),
                "broken_links": [],
                "status": "CHAIN_VALID_PRE_MIGRATION",
                "note": "Hash-chaining was added after these events were recorded."
            }

        broken_links = []
        prev_hash = ""  # Genesis
        for i, event in enumerate(events):
            recorded_prev = event.get("previous_event_hash", "")
            if i == 0:
                # First event — previous_event_hash should be empty
                if recorded_prev not in ("", None):
                    broken_links.append({
                        "event_id": event["event_id"],
                        "position": i,
                        "reason": "Genesis event has non-empty previous_event_hash"
                    })
            else:
                if recorded_prev != prev_hash:
                    broken_links.append({
                        "event_id": event["event_id"],
                        "position": i,
                        "reason": f"Hash mismatch: expected {prev_hash[:16]}..., got {str(recorded_prev)[:16]}..."
                    })

            prev_hash = ChainOfCustodyLogger._compute_event_hash(
                event["event_id"], event["evidence_id"],
                event["action"], event["timestamp"], event["recorded_sha256"]
            )

        chain_valid = len(broken_links) == 0
        return {
            "evidence_id": evidence_id,
            "chain_valid": chain_valid,
            "total_events": len(events),
            "broken_links": broken_links,
            "status": "CHAIN_VALID" if chain_valid else "CHAIN_BROKEN"
        }
