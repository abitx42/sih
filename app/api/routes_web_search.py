"""
app/api/routes_web_search.py
============================
Endpoints for Internet Cross-Check, Reverse Image/Video Search & News Fact-Check Research.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import EVIDENCE_DIR, FORENSIC_DIR
from app.database import get_db
from app.analyzers.internet_search_analyzer import InternetSearchAnalyzer
from app.core.provenance_web import WebProvenanceEngine
from app.core.chain_of_custody import ChainOfCustodyLogger

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Internet Cross-Check & Web Provenance"])


class ArticleResearchRequest(BaseModel):
    query: Optional[str] = None


@router.post("/api/evidence/{evidence_id}/web-search")
def run_web_search_and_provenance(
    evidence_id: str,
    custom_query: Optional[str] = Query(None)
):
    """
    Execute full internet cross-check, reverse search, and news article research pipeline.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        ev = cursor.fetchone()

    if not ev:
        raise HTTPException(status_code=404, detail="Evidence exhibit not found.")

    file_path = EVIDENCE_DIR / ev["stored_filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Evidence media file missing from storage.")

    # 1. Run Internet Search Analyzer (Multi-scale pHash + Reverse search + Diff)
    analyzer = InternetSearchAnalyzer()
    search_res = analyzer.analyze(
        file_path=file_path,
        evidence_id=evidence_id,
        modality=ev.get("modality", "IMAGE"),
        custom_query=custom_query
    )

    # 2. Run News & Fact-Check Article Research
    article_res = WebProvenanceEngine.research_articles(
        evidence_id=evidence_id,
        best_match=search_res.get("best_match"),
        all_matches=search_res.get("all_matches", []),
        custom_query=custom_query
    )

    # 3. Store / Cache in Database
    now = datetime.utcnow().isoformat() + "Z"
    search_id = f"WS-{evidence_id}"
    best_m = search_res.get("best_match") or {}
    diff_data = search_res.get("difference_analysis") or {}

    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS web_search_results (
                search_id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL UNIQUE,
                match_status TEXT NOT NULL,
                match_type TEXT NOT NULL,
                best_match_title TEXT,
                best_match_url TEXT,
                best_match_source TEXT,
                match_confidence REAL NOT NULL,
                match_region TEXT,
                authentic_percentage REAL,
                altered_percentage REAL,
                diff_heatmap_path TEXT,
                articles_json TEXT DEFAULT '[]',
                consensus_verdict TEXT,
                consensus_summary TEXT,
                raw_search_json TEXT DEFAULT '{}',
                searched_at TEXT NOT NULL,
                FOREIGN KEY (evidence_id) REFERENCES evidence (evidence_id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO web_search_results (
                search_id, evidence_id, match_status, match_type,
                best_match_title, best_match_url, best_match_source,
                match_confidence, match_region, authentic_percentage,
                altered_percentage, diff_heatmap_path, articles_json,
                consensus_verdict, consensus_summary, raw_search_json, searched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            search_id,
            evidence_id,
            search_res["match_status"],
            search_res["match_type"],
            best_m.get("title"),
            best_m.get("url"),
            best_m.get("source"),
            search_res["match_confidence"],
            search_res["match_region"],
            diff_data.get("authentic_percentage"),
            diff_data.get("altered_percentage"),
            diff_data.get("diff_heatmap_url"),
            json.dumps(article_res.get("articles", [])),
            article_res.get("consensus_verdict"),
            article_res.get("consensus_summary"),
            json.dumps(search_res),
            now
        ))

    # 4. Record Chain of Custody Event
    ChainOfCustodyLogger.record_event(
        evidence_id=evidence_id,
        action="INTERNET_CROSS_CHECK_COMPLETED",
        actor="Truth Lens Provenance Subsystem",
        recorded_sha256=ev["sha256_hash"],
        details=(
            f"Internet reverse search completed. Match Outcome: {search_res['match_type']}. "
            f"Consensus Verdict: {article_res.get('consensus_verdict')}. "
            f"Source Articles Identified: {len(article_res.get('articles', []))}."
        )
    )

    return {
        "success": True,
        "evidence_id": evidence_id,
        "search_results": search_res,
        "provenance_articles": article_res,
        "searched_at": now
    }


@router.get("/api/evidence/{evidence_id}/web-search")
def get_web_search_results(evidence_id: str):
    """
    Retrieve stored internet search and article research results for an exhibit.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='web_search_results'")
        if not cursor.fetchone():
            return None
        cursor.execute("SELECT * FROM web_search_results WHERE evidence_id = ?", (evidence_id,))
        row = cursor.fetchone()

    if not row:
        # Run on the fly if not yet cached
        try:
            return run_web_search_and_provenance(evidence_id)
        except Exception:
            return None

    articles = []
    try:
        articles = json.loads(row.get("articles_json") or "[]")
    except Exception:
        pass

    raw_search = {}
    try:
        raw_search = json.loads(row.get("raw_search_json") or "{}")
    except Exception:
        pass

    return {
        "evidence_id": evidence_id,
        "search_id": row["search_id"],
        "match_status": row["match_status"],
        "match_type": row["match_type"],
        "match_confidence": row["match_confidence"],
        "match_region": row["match_region"],
        "best_match": {
            "title": row["best_match_title"],
            "url": row["best_match_url"],
            "source": row["best_match_source"]
        } if row.get("best_match_title") else None,
        "difference_analysis": {
            "authentic_percentage": row.get("authentic_percentage"),
            "altered_percentage": row.get("altered_percentage"),
            "matched_region": row.get("match_region"),
            "diff_heatmap_url": row.get("diff_heatmap_path")
        } if row.get("authentic_percentage") is not None else None,
        "provenance_articles": {
            "articles": articles,
            "consensus_verdict": row.get("consensus_verdict"),
            "consensus_summary": row.get("consensus_summary")
        },
        "raw_search": raw_search,
        "searched_at": row["searched_at"]
    }


@router.get("/api/evidence/{evidence_id}/forensic-artifact/web_match_diff")
def get_web_match_diff_artifact(evidence_id: str):
    """Serve the difference heatmap comparing evidence against identified web match."""
    path = FORENSIC_DIR / f"web_match_diff_{evidence_id}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Web match difference map artifact not found.")
    return FileResponse(str(path), media_type="image/png")
