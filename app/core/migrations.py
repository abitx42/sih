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
            ("003_external_api_ledgers", "External API rate limiting and consensus metadata", cls._m003_external_ledgers)
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
                except Exception as e:
                    logger.warning(f"Migration notice for {m_id}: {e}")
                    cursor.execute(
                        "INSERT OR IGNORE INTO _schema_migrations (migration_id, applied_at, description) VALUES (?, ?, ?)",
                        (m_id, datetime.utcnow().isoformat() + "Z", desc)
                    )

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
