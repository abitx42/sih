"""
Tests for hash-chained Chain of Custody logger.
"""
import pytest
from unittest.mock import patch, MagicMock, call


def _mock_db_context(rows=None):
    """Returns a mock get_db context that yields a cursor returning the given rows."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows or []
    mock_cursor.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    return mock_conn


def test_compute_event_hash_is_deterministic():
    from app.core.chain_of_custody import ChainOfCustodyLogger
    h1 = ChainOfCustodyLogger._compute_event_hash("EV1", "E1", "UPLOAD", "2026-01-01T00:00:00Z", "abc")
    h2 = ChainOfCustodyLogger._compute_event_hash("EV1", "E1", "UPLOAD", "2026-01-01T00:00:00Z", "abc")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_compute_event_hash_differs_on_different_inputs():
    from app.core.chain_of_custody import ChainOfCustodyLogger
    h1 = ChainOfCustodyLogger._compute_event_hash("EV1", "E1", "UPLOAD", "2026-01-01T00:00:00Z", "abc")
    h2 = ChainOfCustodyLogger._compute_event_hash("EV1", "E1", "ANALYZE", "2026-01-01T00:00:00Z", "abc")
    assert h1 != h2


def test_verify_chain_empty_returns_valid():
    from app.core.chain_of_custody import ChainOfCustodyLogger
    with patch("app.core.chain_of_custody.get_db") as mock_db:
        mock_conn = _mock_db_context(rows=[])
        mock_db.return_value = mock_conn
        result = ChainOfCustodyLogger.verify_chain("EV-EMPTY")
        assert result["chain_valid"] is True
        assert result["total_events"] == 0
        assert result["status"] == "CHAIN_EMPTY"


def test_verify_chain_valid_linked_events():
    """Simulate two properly linked events."""
    from app.core.chain_of_custody import ChainOfCustodyLogger

    # Compute the expected hash of event 1 to use as event 2's previous_event_hash
    ev1_hash = ChainOfCustodyLogger._compute_event_hash(
        "COC-0001", "EV-001", "UPLOAD", "2026-01-01T00:00:01Z", "sha1"
    )

    events = [
        {
            "event_id": "COC-0001",
            "evidence_id": "EV-001",
            "action": "UPLOAD",
            "timestamp": "2026-01-01T00:00:01Z",
            "recorded_sha256": "sha1",
            "previous_event_hash": ""  # genesis
        },
        {
            "event_id": "COC-0002",
            "evidence_id": "EV-001",
            "action": "ANALYZE",
            "timestamp": "2026-01-01T00:00:02Z",
            "recorded_sha256": "sha1",
            "previous_event_hash": ev1_hash  # correct link
        }
    ]

    with patch("app.core.chain_of_custody.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # First call: PRAGMA table_info → return "previous_event_hash" column
        mock_cursor.fetchall.side_effect = [
            [{"name": "event_id"}, {"name": "previous_event_hash"}],
            events
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        result = ChainOfCustodyLogger.verify_chain("EV-001")
        assert result["chain_valid"] is True
        assert len(result["broken_links"]) == 0
        assert result["status"] == "CHAIN_VALID"


def test_verify_chain_detects_tampered_event():
    """Simulate a broken link where previous_event_hash was tampered."""
    from app.core.chain_of_custody import ChainOfCustodyLogger

    events = [
        {
            "event_id": "COC-0001",
            "evidence_id": "EV-001",
            "action": "UPLOAD",
            "timestamp": "2026-01-01T00:00:01Z",
            "recorded_sha256": "sha1",
            "previous_event_hash": ""  # genesis
        },
        {
            "event_id": "COC-0002",
            "evidence_id": "EV-001",
            "action": "ANALYZE",
            "timestamp": "2026-01-01T00:00:02Z",
            "recorded_sha256": "sha1",
            "previous_event_hash": "TAMPERED_HASH_VALUE_000000000000000000000000000000000000000000"
        }
    ]

    with patch("app.core.chain_of_custody.get_db") as mock_db:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = [
            [{"name": "event_id"}, {"name": "previous_event_hash"}],
            events
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_db.return_value = mock_conn

        result = ChainOfCustodyLogger.verify_chain("EV-001")
        assert result["chain_valid"] is False
        assert len(result["broken_links"]) == 1
        assert result["status"] == "CHAIN_BROKEN"
        assert result["broken_links"][0]["event_id"] == "COC-0002"
