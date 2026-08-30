from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import FileResponse
from app.database import get_db
from app.config import REPORTS_DIR
from app.core.report_generator import ForensicReportGenerator
from app.core.chain_of_custody import ChainOfCustodyLogger

router = APIRouter(prefix="/api/reports", tags=["Reports"])

def _extract_officer_name(authorization: Optional[str], default_actor: str = "Lead Forensic Examiner") -> str:
    if authorization and authorization.startswith("Bearer "):
        try:
            from app.core.auth import decode_access_token
            payload = decode_access_token(authorization.split(" ")[1])
            if payload and payload.get("name"):
                return str(payload["name"]).strip()
        except Exception:
            pass
    return str(default_actor).strip() or "Lead Forensic Examiner"

@router.get("/{evidence_id}/download")
@router.get("/{evidence_id}/pdf")
def generate_and_download_report(evidence_id: str, actor: str = "Lead Forensic Examiner", authorization: Optional[str] = Header(None)):
    officer_name = _extract_officer_name(authorization, actor)
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

@router.get("/cases/{case_id}/download")
def generate_and_download_case_report(case_id: str, actor: str = "Lead Forensic Examiner"):
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Case
        cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
        case_info = cursor.fetchone()
        if not case_info:
            raise HTTPException(status_code=404, detail="Case not found.")

        # 2. Evidence with forensic results
        cursor.execute("""
        SELECT 
            e.evidence_id, e.case_id, e.original_filename, e.modality, e.file_size_bytes,
            e.sha256_hash, e.uploaded_by, e.uploaded_at, e.status, e.analyzed_at,
            fr.forensic_risk_score, fr.risk_category, fr.model_status
        FROM evidence e
        LEFT JOIN forensic_results fr ON e.evidence_id = fr.evidence_id
        WHERE e.case_id = ?
        ORDER BY e.uploaded_at DESC
        """, (case_id,))
        evidence_items = cursor.fetchall()

        # 3. Case Summary stats
        status_counts = {"ANALYZING": 0, "COMPLETED": 0, "FAILED": 0}
        risk_counts = {"LOW RISK": 0, "REVIEW REQUIRED": 0, "HIGH RISK": 0}
        for item in evidence_items:
            st = item["status"]
            status_counts[st] = status_counts.get(st, 0) + 1
            rc = item.get("risk_category")
            if rc in risk_counts:
                risk_counts[rc] += 1
        summary_data = {
            "total_evidence": len(evidence_items),
            "status_counts": status_counts,
            "risk_counts": risk_counts
        }

        # 4. Custody events
        cursor.execute("""
        SELECT coc.*
        FROM chain_of_custody coc
        JOIN evidence e ON coc.evidence_id = e.evidence_id
        WHERE e.case_id = ?
        ORDER BY coc.timestamp DESC
        LIMIT 100
        """, (case_id,))
        custody_events = cursor.fetchall()

    pdf_path = ForensicReportGenerator.generate_case_summary_pdf(
        case_data=case_info,
        summary_data=summary_data,
        evidence_items=evidence_items,
        custody_events=custody_events
    )

    if evidence_items:
        ChainOfCustodyLogger.record_event(
            evidence_id=evidence_items[0]["evidence_id"],
            action="CASE_REPORT_EXPORTED",
            actor=actor,
            recorded_sha256=evidence_items[0]["sha256_hash"],
            details=f"Truth Lens Case investigation summary PDF report exported for case '{case_id}' ({len(evidence_items)} exhibits)."
        )

    return FileResponse(
        path=str(pdf_path),
        filename=pdf_path.name,
        media_type="application/pdf"
    )


# =========================================================================
# SECTION 65B (BSA 2023) LEGAL COURTROOM CERTIFICATE ENDPOINTS
# =========================================================================

@router.get("/{evidence_id}/certificate/bsa-65b")
def get_legal_certificate_payload(evidence_id: str):
    """
    Returns structured Section 65B(4) / Section 63 BSA 2023 legal certificate data.
    """
    from app.core.legal_certificate import LegalCertificateGenerator
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

        cursor.execute("SELECT * FROM cases WHERE case_id = ?", (evidence["case_id"],))
        case_info = cursor.fetchone() or {"case_id": "CASE-2026-001", "title": "General Investigation"}

        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        forensic_res = cursor.fetchone()
        if not forensic_res:
            raise HTTPException(status_code=400, detail="Forensic analysis must be completed first.")

    return LegalCertificateGenerator.create_certificate_payload(
        evidence=evidence,
        case=case_info,
        forensic_res=forensic_res
    )


@router.get("/{evidence_id}/certificate-pdf")
def download_legal_certificate_pdf(evidence_id: str, actor: str = "Lead Forensic Examiner", authorization: Optional[str] = Header(None)):
    """
    Compiles and downloads official certified Section 65B (BSA 2023) PDF Annexure.
    """
    from app.core.legal_certificate import LegalCertificateGenerator
    officer_name = _extract_officer_name(authorization, actor)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        evidence = cursor.fetchone()
        if not evidence:
            raise HTTPException(status_code=404, detail="Evidence not found.")

        cursor.execute("SELECT * FROM cases WHERE case_id = ?", (evidence["case_id"],))
        case_info = cursor.fetchone() or {"case_id": "CASE-2026-001", "title": "General Investigation"}

        cursor.execute("SELECT * FROM forensic_results WHERE evidence_id = ?", (evidence_id,))
        forensic_res = cursor.fetchone()
        if not forensic_res:
            raise HTTPException(status_code=400, detail="Forensic analysis must be completed first.")

    pdf_path = LegalCertificateGenerator.generate_pdf(
        evidence=evidence,
        case=case_info,
        forensic_res=forensic_res,
        officer_name=officer_name
    )

    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="LEGAL_CERTIFICATE_BSA65B_EXPORTED",
        actor=officer_name,
        recorded_sha256=evidence["sha256_hash"],
        details=f"Official Section 65B (BSA 2023) Court Certificate exported: '{pdf_path.name}'."
    )

    return FileResponse(
        path=str(pdf_path),
        filename=pdf_path.name,
        media_type="application/pdf"
    )
