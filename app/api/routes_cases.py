import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException
from app.database import get_db
from app.models.schemas import CaseCreate, CaseResponse

router = APIRouter(prefix="/api/cases", tags=["Cases"])

@router.get("", response_model=List[CaseResponse])
def list_cases():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT c.*, COUNT(e.evidence_id) as evidence_count
        FROM cases c
        LEFT JOIN evidence e ON c.case_id = e.case_id
        GROUP BY c.case_id
        ORDER BY c.created_at DESC
        """)
        return cursor.fetchall()

@router.post("", response_model=CaseResponse)
def create_case(case_in: CaseCreate):
    case_id = case_in.case_id or f"CASE-2026-{uuid.uuid4().hex[:4].upper()}"
    created_at = datetime.utcnow().isoformat() + "Z"

    with get_db() as conn:
        cursor = conn.cursor()
        # Check duplicate
        cursor.execute("SELECT case_id FROM cases WHERE case_id = ?", (case_id,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail=f"Case ID '{case_id}' already exists.")

        cursor.execute("""
        INSERT INTO cases (case_id, title, description, lead_investigator, created_at, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            case_id,
            case_in.title,
            case_in.description or "",
            case_in.lead_investigator,
            created_at,
            "ACTIVE"
        ))

    return {
        "case_id": case_id,
        "title": case_in.title,
        "description": case_in.description,
        "lead_investigator": case_in.lead_investigator,
        "created_at": created_at,
        "status": "ACTIVE",
        "evidence_count": 0
    }

@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT c.*, COUNT(e.evidence_id) as evidence_count
        FROM cases c
        LEFT JOIN evidence e ON c.case_id = e.case_id
        WHERE c.case_id = ?
        GROUP BY c.case_id
        """, (case_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Case not found.")
        return row
