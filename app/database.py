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
            pipeline_status TEXT NOT NULL DEFAULT 'PENDING',
            analysis_started_at TEXT,
            analyzed_at TEXT,
            error_message TEXT,
            notes TEXT,
            FOREIGN KEY (case_id) REFERENCES cases (case_id) ON DELETE CASCADE
        )
        """)
        
        # Migration helper: ensure new columns exist if table was created previously
        cursor.execute("PRAGMA table_info(evidence)")
        ev_columns = [col["name"] for col in cursor.fetchall()]
        if "pipeline_status" not in ev_columns:
            cursor.execute("ALTER TABLE evidence ADD COLUMN pipeline_status TEXT DEFAULT 'COMPLETED'")
        if "analysis_started_at" not in ev_columns:
            cursor.execute("ALTER TABLE evidence ADD COLUMN analysis_started_at TEXT")
        if "analyzed_at" not in ev_columns:
            cursor.execute("ALTER TABLE evidence ADD COLUMN analyzed_at TEXT")
        if "error_message" not in ev_columns:
            cursor.execute("ALTER TABLE evidence ADD COLUMN error_message TEXT")
        if "analysis_mode" not in ev_columns:
            cursor.execute("ALTER TABLE evidence ADD COLUMN analysis_mode TEXT DEFAULT 'FULL_ANALYSIS'")
        if "pipeline_stages_json" not in ev_columns:
            cursor.execute("ALTER TABLE evidence ADD COLUMN pipeline_stages_json TEXT DEFAULT '{}'")
        if "dna_fingerprint" not in ev_columns:
            cursor.execute("ALTER TABLE evidence ADD COLUMN dna_fingerprint TEXT")
        if "phash" not in ev_columns:
            cursor.execute("ALTER TABLE evidence ADD COLUMN phash TEXT")

        # 3. Forensic Results Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS forensic_results (
            result_id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL UNIQUE,
            integrity_status TEXT NOT NULL,
            provenance_status TEXT NOT NULL,
            ai_manipulation_score REAL,
            ai_manipulation_indicator REAL,
            ai_model_name TEXT NOT NULL,
            ai_model_version TEXT,
            model_confidence REAL,
            model_status TEXT NOT NULL DEFAULT 'AVAILABLE',
            forensic_anomaly_score REAL NOT NULL DEFAULT 0.0,
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

        # Migration helper: ensure new columns exist if table was created previously
        cursor.execute("PRAGMA table_info(forensic_results)")
        columns = [col["name"] for col in cursor.fetchall()]
        if "ai_manipulation_indicator" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN ai_manipulation_indicator REAL")
        if "ai_model_version" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN ai_model_version TEXT")
        if "model_confidence" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN model_confidence REAL")
        if "model_status" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN model_status TEXT DEFAULT 'AVAILABLE'")
        if "forensic_anomaly_score" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN forensic_anomaly_score REAL DEFAULT 0.0")
        if "ensemble_agreement_json" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN ensemble_agreement_json TEXT DEFAULT '{}'")
        if "manipulation_subtype" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN manipulation_subtype TEXT DEFAULT 'INCONCLUSIVE'")
        if "reproducibility_json" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN reproducibility_json TEXT DEFAULT '{}'")
        if "localization_status" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN localization_status TEXT DEFAULT 'UNAVAILABLE'")
        if "localization_json" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN localization_json TEXT DEFAULT '{}'")
        if "policy_outcome" not in columns:
            cursor.execute("ALTER TABLE forensic_results ADD COLUMN policy_outcome TEXT DEFAULT 'INCONCLUSIVE'")

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

        # Migration: add previous_event_hash for hash-chained audit log
        cursor.execute("PRAGMA table_info(chain_of_custody)")
        coc_columns = [col["name"] for col in cursor.fetchall()]
        if "previous_event_hash" not in coc_columns:
            cursor.execute("ALTER TABLE chain_of_custody ADD COLUMN previous_event_hash TEXT DEFAULT ''")

        # 6. Investigator Reviews Table (Phase 3B)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS investigator_reviews (
            review_id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            verdict TEXT NOT NULL,
            notes TEXT,
            reviewer_name TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            FOREIGN KEY (evidence_id) REFERENCES evidence (evidence_id) ON DELETE CASCADE
        )
        """)

        # 7. Reference Comparisons Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reference_comparisons (
            comparison_id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            reference_sha256 TEXT NOT NULL,
            reference_filename TEXT NOT NULL,
            comparison_status TEXT NOT NULL,
            ssim_score REAL,
            alignment_succeeded INTEGER NOT NULL DEFAULT 0,
            difference_map_path TEXT,
            changed_region_count INTEGER NOT NULL DEFAULT 0,
            submitted_at TEXT NOT NULL,
            submitted_by TEXT NOT NULL DEFAULT 'Investigator',
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


def reconcile_orphaned_jobs() -> int:
    """
    On application startup, scans for evidence records left in status 'ANALYZING' 
    due to an unexpected server interruption/restart and transitions them to 'FAILED'.
    Logs an ANALYSIS_FAILED event in the chain of custody.
    """
    import uuid
    now = datetime.utcnow().isoformat() + "Z"
    safe_msg = "Analysis interrupted by server restart. Please retry the upload."
    recovered = 0
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT evidence_id, sha256_hash FROM evidence WHERE status = 'ANALYZING' OR pipeline_status = 'ANALYZING'")
        stale_records = cursor.fetchall()
        for rec in stale_records:
            ev_id = rec["evidence_id"]
            cursor.execute("""
            UPDATE evidence
            SET status = 'FAILED', pipeline_status = 'FAILED', error_message = ?, analyzed_at = ?
            WHERE evidence_id = ?
            """, (safe_msg, now, ev_id))
            recovered += 1

            event_id = f"COC-{uuid.uuid4().hex[:10].upper()}"
            cursor.execute("""
            INSERT INTO chain_of_custody (event_id, evidence_id, action, actor, recorded_sha256, details, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (event_id, ev_id, "ANALYSIS_FAILED", "Truth Lens System Recovery", rec["sha256_hash"], f"Job recovery: {safe_msg}", now))

    return recovered

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
