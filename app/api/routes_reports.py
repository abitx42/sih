import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.database import get_db
from app.config import REPORTS_DIR
from app.core.report_generator import ForensicReportGenerator
from app.core.chain_of_custody import ChainOfCustodyLogger

router = APIRouter(prefix="/api/reports", tags=["Reports"])

@router.get("/{evidence_id}/download")
def generate_and_download_report(evidence_id: str, actor: str = "Lead Forensic Examiner"):
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Evidence
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

        # 2. Case
        cursor.execute("SELECT * FROM cases WHERE case_id = ?", (evidence["case_id"],))
        case_info = cursor.fetchone() or {"case_id": "UNKNOWN", "title": "General Case", "lead_investigator": "Forensic Officer"}

        # 3. Forensic Results
        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        forensic_res = cursor.fetchone()
        if not forensic_res:
            raise HTTPException(status_code=400, detail="Forensic analysis must be completed before generating report.")

        # 4. Findings
        cursor.execute("SELECT * FROM findings WHERE evidence_id = ? ORDER BY score DESC", (evidence_id,))
        findings = cursor.fetchall()

        # 5. Custody events
        cursor.execute("SELECT * FROM chain_of_custody WHERE evidence_id = ? ORDER BY timestamp ASC", (evidence_id,))
        custody_events = cursor.fetchall()

    # Generate PDF
    pdf_path = ForensicReportGenerator.generate_pdf(
        evidence_data=evidence,
        case_data=case_info,
        forensic_result=forensic_res,
        findings=findings,
        custody_events=custody_events
    )

    # Log report generation event in chain of custody
    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="FORENSIC_REPORT_EXPORTED",
        actor=actor,
        recorded_sha256=evidence["sha256_hash"],
        details=f"Truth Lens forensic assessment PDF report generated: '{pdf_path.name}'."
    )

    return FileResponse(
        path=str(pdf_path),
        filename=pdf_path.name,
        media_type="application/pdf"
    )
