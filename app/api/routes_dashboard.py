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
        WHERE risk_category IS NOT NULL 
        GROUP BY risk_category
        """)
        risk_dist = {"HIGH RISK": 0, "LOW RISK": 0, "REVIEW REQUIRED": 0}
        for r in cursor.fetchall():
            if r["risk_category"]:
                risk_dist[r["risk_category"]] = r["count"]

        # 4. Modality Distribution
        cursor.execute("""
        SELECT modality, COUNT(*) as count 
        FROM evidence 
        WHERE modality IS NOT NULL 
        GROUP BY modality
        """)
        modality_dist = {r["modality"]: r["count"] for r in cursor.fetchall()}

        # 5. Processing Status
        cursor.execute("""
        SELECT status, COUNT(*) as count 
        FROM evidence 
        GROUP BY status
        """)
        processing_status = {r["status"]: r["count"] for r in cursor.fetchall()}

        # 6. Recent Activity & Custody Events
        cursor.execute("""
        SELECT * FROM evidence 
        ORDER BY uploaded_at DESC 
        LIMIT 10
        """)
        recent_activity = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
        SELECT * FROM chain_of_custody 
        ORDER BY timestamp DESC 
        LIMIT 10
        """)
        recent_custody = [dict(row) for row in cursor.fetchall()]

    return {
        "total_cases": total_cases,
        "total_evidence": total_evidence,
        "risk_distribution": risk_dist,
        "modality_distribution": modality_dist,
        "processing_status": processing_status,
        "recent_activity": recent_activity,
        "recent_evidence": recent_activity,
        "recent_custody_events": recent_custody
    }
