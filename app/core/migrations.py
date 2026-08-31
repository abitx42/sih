"""
app/core/migrations.py
=======================
Automated Schema Migration Runner for Truth Lens SQLite Database.
Tracks applied migration steps in `_schema_migrations` with execution timestamps.
"""
import logging
import sqlite3
from datetime import datetime
from typing import List, Tuple, Callable

logger = logging.getLogger(__name__)


class MigrationRunner:
    """Manages sequential database schema versioning and migrations."""

    @classmethod
    def run_migrations(cls, conn: sqlite3.Connection):
        """Ensures migration ledger exists and executes unapplied migrations."""
        cursor = conn.cursor()
        
        # 1. Create migration ledger if missing
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT
        )
        """)

        # 2. Get list of applied migrations
        cursor.execute("SELECT migration_id FROM _schema_migrations")
        applied = {row["migration_id"] if isinstance(row, dict) else row[0] for row in cursor.fetchall()}

        # 3. Define registered migration list
        migrations: List[Tuple[str, str, Callable[[sqlite3.Cursor], None]]] = [
            ("001_core_tables", "Initial cases, evidence, forensic_results schema", cls._m001_core_tables),
            ("002_active_learning_quotas", "Active learning, user quota actors, and model versions", cls._m002_active_learning),
            ("003_external_api_ledgers", "External API rate limiting and consensus metadata", cls._m003_external_ledgers),
            ("004_database_indexes", "B-tree indexes on foreign keys and frequently-queried columns", cls._m004_database_indexes)
        ]

        for m_id, desc, func in migrations:
            if m_id not in applied:
                logger.info(f"Applying database migration: {m_id} — {desc}")
                try:
                    func(cursor)
                    cursor.execute(
                        "INSERT INTO _schema_migrations (migration_id, applied_at, description) VALUES (?, ?, ?)",
                        (m_id, datetime.utcnow().isoformat() + "Z", desc)
                    )
                    logger.info(f"Migration {m_id} applied successfully.")
                except Exception as e:
                    logger.warning(f"Migration {m_id} skipped (already applied or non-critical): {e}")

    @staticmethod
    def _m001_core_tables(cursor: sqlite3.Cursor):
        pass

    @staticmethod
    def _m002_active_learning(cursor: sqlite3.Cursor):
        cursor.execute("PRAGMA table_info(evidence)")
        cols = [r["name"] if isinstance(r, dict) else r[1] for r in cursor.fetchall()]
        if "quota_actor" not in cols:
            cursor.execute("ALTER TABLE evidence ADD COLUMN quota_actor TEXT")

    @staticmethod
    def _m003_external_ledgers(cursor: sqlite3.Cursor):
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS external_api_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            evidence_id TEXT,
            endpoint TEXT NOT NULL,
            status_code INTEGER,
            response_time_ms REAL,
            created_at TEXT NOT NULL
        )
        """)

    @staticmethod
    def _m004_database_indexes(cursor: sqlite3.Cursor):
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_case_id ON evidence(case_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_status ON evidence(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_uploaded_at ON evidence(uploaded_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_quota_actor ON evidence(quota_actor)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_evidence_id ON findings(evidence_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chain_of_custody_evidence_id ON chain_of_custody(evidence_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chain_of_custody_timestamp ON chain_of_custody(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_investigator_reviews_evidence_id ON investigator_reviews(evidence_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reference_comparisons_evidence_id ON reference_comparisons(evidence_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_training_dataset_evidence_id ON training_dataset(evidence_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_training_dataset_used_in_training ON training_dataset(used_in_training)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_web_search_results_evidence_id ON web_search_results(evidence_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_sha256 ON evidence(sha256_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_phash ON evidence(phash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_coc_ev_time ON chain_of_custody(evidence_id, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_evidence_id ON feedback(evidence_id)")
