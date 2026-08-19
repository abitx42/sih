import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.database import get_db
from app.models.schemas import CopilotQueryRequest, CopilotQueryResponse
from app.core.copilot import ForensicCopilot

router = APIRouter(prefix="/api/copilot", tags=["Forensic Copilot"])

@router.post("/query", response_model=CopilotQueryResponse)
def query_copilot(req: CopilotQueryRequest):
    evidence_id = req.evidence_id
    question = req.question

    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get evidence
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

        # Get forensic result
        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        forensic_res = cursor.fetchone()
        if forensic_res:
            try:
                forensic_res["raw_metrics_json"] = json.loads(forensic_res["raw_metrics_json"])
            except Exception:
                forensic_res["raw_metrics_json"] = {}

        # Get findings
        cursor.execute("SELECT * FROM findings WHERE evidence_id = ?", (evidence_id,))
        findings = cursor.fetchall()

    evidence_detail = {
        "evidence": evidence,
        "forensic_result": forensic_res,
        "findings": findings
    }

    copilot_result = ForensicCopilot.answer_investigator_query(
        evidence_id=evidence_id,
        question=question,
        evidence_detail=evidence_detail
    )

    return {
        "evidence_id": evidence_id,
        "question": question,
        "answer": copilot_result["answer"],
        "source": copilot_result["source"],
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
