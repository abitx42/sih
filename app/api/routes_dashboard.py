from typing import Dict, Any, List
from fastapi import APIRouter
from app.database import get_db

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/stats")
def get_dashboard_stats():
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Total Cases
        cursor.execute("SELECT COUNT(*) as count FROM cases")
        total_cases = cursor.fetchone()["count"]

        # 2. Total Evidence
        cursor.execute("SELECT COUNT(*) as count FROM evidence")
        total_evidence = cursor.fetchone()["count"]

        # 3. Risk Distribution
        cursor.execute("""
        SELECT risk_category, COUNT(*) as count
        FROM forensic_results
        GROUP BY risk_category
        """)
        risk_rows = cursor.fetchall()
        risk_dist = {"LOW RISK": 0, "REVIEW REQUIRED": 0, "HIGH RISK": 0}
        for r in risk_rows:
            risk_dist[r["risk_category"]] = r["count"]

        # 4. Modality Distribution
        cursor.execute("""
        SELECT modality, COUNT(*) as count
        FROM evidence
        GROUP BY modality
        """)
        modality_rows = cursor.fetchall()
        mod_dist = {}
        for m in modality_rows:
            mod_dist[m["modality"]] = m["count"]

        # 5. Recent Evidence
        cursor.execute("""
        SELECT e.*, r.forensic_risk_score, r.risk_category
        FROM evidence e
        LEFT JOIN forensic_results r ON e.evidence_id = r.evidence_id
        ORDER BY e.uploaded_at DESC
        LIMIT 6
        """)
        recent_evidence = cursor.fetchall()

        # 6. Recent Custody Stream
        cursor.execute("""
        SELECT * FROM chain_of_custody
        ORDER BY timestamp DESC
        LIMIT 8
        """)
        recent_custody = cursor.fetchall()

    return {
        "total_cases": total_cases,
        "total_evidence": total_evidence,
        "risk_distribution": risk_dist,
        "modality_distribution": mod_dist,
        "recent_evidence": recent_evidence,
        "recent_custody_events": recent_custody
    }
