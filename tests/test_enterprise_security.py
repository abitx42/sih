"""
tests/test_enterprise_security.py
=================================
Tests for Enterprise HTTP Security Headers, Anti-Brute-Force Rate Limiting,
Path Traversal Defense, Filename Sanitization, and Proprietary Licensing.
"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.core.security_guard import sanitize_filename, validate_safe_path
from app.core.rate_limiter import SlidingWindowRateLimiter

client = TestClient(app)


def test_security_headers_present_on_all_responses():
    """Verify enterprise HTTP security headers are injected on responses."""
    res = client.get("/")
    assert res.status_code == 200

    # 1. Content Security Policy
    assert "Content-Security-Policy" in res.headers
    csp = res.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp

    # 2. Anti-Clickjacking
    assert res.headers.get("X-Frame-Options") == "DENY"

    # 3. MIME Sniffing Prevention
    assert res.headers.get("X-Content-Type-Options") == "nosniff"

    # 4. Referrer Policy
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    # 5. Permissions Policy
    assert "camera=()" in res.headers.get("Permissions-Policy", "")


def test_api_cache_control_headers():
    """Verify sensitive API responses are flagged with no-store to prevent browser disk caching."""
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    assert "no-store" in res.headers.get("Cache-Control", "")
    assert "no-cache" in res.headers.get("Pragma", "")


def test_sliding_window_rate_limiter_logic():
    """Verify sliding window rate limiter throttles excessive requests."""
    limiter = SlidingWindowRateLimiter()
    test_ip = "198.51.100.42"

    # Allowed within limit (limit = 3)
    for _ in range(3):
        allowed, count, retry_after = limiter.is_allowed(test_ip, limit=3, window_seconds=60.0)
        assert allowed is True

    # 4th request must be blocked
    allowed, count, retry_after = limiter.is_allowed(test_ip, limit=3, window_seconds=60.0)
    assert allowed is False
    assert retry_after > 0


def test_filename_sanitization_defense():
    """Verify path traversal and malicious double extensions are neutralized."""
    # Path traversal attack
    assert sanitize_filename("../../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\Windows\\System32\\cmd.exe") == "cmd.blocked"

    # Dangerous double extensions
    assert sanitize_filename("innocent_pic.jpg.exe") == "innocent_pic.jpg.blocked"
    assert sanitize_filename("shell.php") == "shell.blocked"
    assert sanitize_filename("script.sh") == "script.blocked"

    # Clean file
    assert sanitize_filename("investigation_photo.png") == "investigation_photo.png"


def test_validate_safe_path_boundary_isolation():
    """Verify path boundary containment prevents escaping designated storage sandbox."""
    from app.config import STORAGE_DIR
    base_dir = STORAGE_DIR / "test_sandbox_dir"
    base_dir.mkdir(parents=True, exist_ok=True)

    safe_file = base_dir / "evidence_01.jpg"
    unsafe_file = base_dir / "../secret.key"

    assert validate_safe_path(safe_file, base_dir) is True
    assert validate_safe_path(unsafe_file, base_dir) is False

    # Cleanup
    try:
        base_dir.rmdir()
    except Exception:
        pass


def test_proprietary_license_file_exists():
    """Verify proprietary commercial license replaces open-source licenses."""
    base_dir = Path(__file__).resolve().parent.parent
    license_file = base_dir / "LICENSE"
    proprietary_file = base_dir / "PROPRIETARY_NOTICE.md"

    assert license_file.exists()
    assert proprietary_file.exists()

    content = license_file.read_text(encoding="utf-8")
    assert "PROPRIETARY & CONFIDENTIAL" in content
    assert "Copyright (c) 2024-2026 Truth Lens" in content
    assert "PROHIBITION OF PUBLIC DISTRIBUTION" in content


def test_forensic_artifact_invalid_type_and_nonexistent_evidence():
    """Verify 400 on illegal artifact types and 404 on nonexistent evidence artifacts."""
    # Invalid artifact type
    res_bad = client.get("/api/evidence/EV-TEST-123/forensic-artifact/malicious_exec")
    assert res_bad.status_code == 400

    # Nonexistent evidence valid type
    res_404 = client.get("/api/evidence/EV-NONEXISTENT-9999/forensic-artifact/ela")
    assert res_404.status_code == 404
