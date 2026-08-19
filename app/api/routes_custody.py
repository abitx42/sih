import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Response
from app.database import get_db
from app.models.schemas import CustodyEventResponse

router = APIRouter(prefix="/api/custody", tags=["Chain of Custody"])

@router.get("", response_model=List[CustodyEventResponse])
def list_custody_events(evidence_id: Optional[str] = None):
    query = "SELECT * FROM chain_of_custody WHERE 1=1"
    params = []
    if evidence_id:
        query += " AND evidence_id = ?"
        params.append(evidence_id)
    query += " ORDER BY timestamp DESC LIMIT 200"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

@router.get("/export")
def export_custody_ledger(evidence_id: Optional[str] = None):
    """
    Exports the append-only application custody log in formatted JSON format.
    """
    query = "SELECT * FROM chain_of_custody WHERE 1=1"
    params = []
    if evidence_id:
        query += " AND evidence_id = ?"
        params.append(evidence_id)
    query += " ORDER BY timestamp ASC"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        events = cursor.fetchall()

    export_payload = {
        "platform": "Truth Lens Digital Evidence Forensics Platform",
        "log_type": "Append-Only Application Custody Log",
        "disclaimer": "Prototype application custody log designed to support forensic workflow documentation. Stored in local SQLite; not an independent cryptographic proof or replacement for formal evidence-management procedures.",
        "filter_evidence_id": evidence_id,
        "total_events": len(events),
        "events": events
    }

    json_str = json.dumps(export_payload, indent=2)
    return Response(
        content=json_str,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=chain_of_custody_{evidence_id or 'all'}.json"
        }
    )
