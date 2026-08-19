import sqlite3
import json
import logging
from datetime import datetime
from contextlib import contextmanager
from app.config import DB_PATH

logger = logging.getLogger(__name__)

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Cases Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            lead_investigator TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
        )
        """)
        
        # 2. Evidence Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            modality TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            sha256_hash TEXT NOT NULL,
            sha512_hash TEXT NOT NULL,
            md5_hash TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'INGESTED',
            notes TEXT,
            FOREIGN KEY (case_id) REFERENCES cases (case_id) ON DELETE CASCADE
        )
        """)
        
        # 3. Forensic Results Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS forensic_results (
            result_id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL UNIQUE,
            integrity_status TEXT NOT NULL,
            provenance_status TEXT NOT NULL,
            ai_manipulation_score REAL NOT NULL,
            ai_model_name TEXT NOT NULL,
            forensic_risk_score REAL NOT NULL,
            risk_category TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            analyzed_at TEXT NOT NULL,
            raw_metrics_json TEXT NOT NULL,
            summary_narrative TEXT,
            recommendations TEXT,
            FOREIGN KEY (evidence_id) REFERENCES evidence (evidence_id) ON DELETE CASCADE
        )
        """)
        
        # 4. Findings Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS findings (
            finding_id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            signal_name TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            score REAL NOT NULL,
            explanation TEXT NOT NULL,
            location_ref TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (evidence_id) REFERENCES evidence (evidence_id) ON DELETE CASCADE
        )
        """)
        
        # 5. Chain of Custody Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chain_of_custody (
            event_id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            recorded_sha256 TEXT NOT NULL,
            details TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (evidence_id) REFERENCES evidence (evidence_id) ON DELETE CASCADE
        )
        """)
        
        # Insert default demo case if no cases exist
        cursor.execute("SELECT COUNT(*) as count FROM cases")
        if cursor.fetchone()["count"] == 0:
            cursor.execute("""
            INSERT INTO cases (case_id, title, description, lead_investigator, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                "CASE-2026-001",
                "Operation CyberShield - Deepfake Verification Audit",
                "Forensic authenticity assessment for critical digital exhibits submitted under SIH PS-27.",
                "Insp. Rajesh Verma (Digital Forensics Unit)",
                datetime.utcnow().isoformat() + "Z",
                "ACTIVE"
            ))
            logger.info("Initialized default case CASE-2026-001")

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
