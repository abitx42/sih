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
        risk_dist = {r["risk_category"]: r["count"] for r in cursor.fetchall()}

        # 4. Processing Status
        cursor.execute("""
        SELECT status, COUNT(*) as count 
        FROM evidence 
        GROUP BY status
        """)
        processing_status = {r["status"]: r["count"] for r in cursor.fetchall()}

        # 5. Recent Activity
        cursor.execute("""
        SELECT * FROM evidence 
        ORDER BY uploaded_at DESC 
        LIMIT 10
        """)
        recent_activity = [dict(row) for row in cursor.fetchall()]

    return {
        "total_cases": total_cases,
        "total_evidence": total_evidence,
        "risk_distribution": risk_dist,
        "processing_status": processing_status,
        "recent_activity": recent_activity
    }
