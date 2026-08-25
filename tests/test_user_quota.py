"""
Test User Quota (Task #19)
Tests for user quota limits across GUEST, STANDARD, and VERIFIED_INVESTIGATOR tiers.
"""
import pytest
from app.core.user_quota import (
    QUOTA_TIERS,
    resolve_tier,
    check_user_quota,
    build_quota_status
)


def test_resolve_tier_guest():
    """GUEST role with is_guest=True stays GUEST."""
    assert resolve_tier("GUEST", is_guest=True) == "GUEST"


def test_resolve_tier_investigator():
    """INVESTIGATOR role with is_guest=False resolves to STANDARD."""
    assert resolve_tier("INVESTIGATOR", is_guest=False) == "STANDARD"


def test_resolve_tier_verified():
    """VERIFIED_INVESTIGATOR role stays VERIFIED_INVESTIGATOR."""
    assert resolve_tier("VERIFIED_INVESTIGATOR", is_guest=False) == "VERIFIED_INVESTIGATOR"


def test_check_user_quota_guest_file_size_exceeded():
    """GUEST users should be rejected for files > 10MB."""
    actor = "test_guest_size@truthlens.ai"
    over_size = 15 * 1024 * 1024  # 15 MB > 10MB limit
    allowed, reason, usage = check_user_quota(
        actor_key=actor,
        role="GUEST",
        is_guest=True,
        incoming_bytes=over_size
    )
    assert not allowed, "GUEST should be rejected for files > 10MB"
    assert "exceeds" in reason.lower() or "limit" in reason.lower()


def test_check_user_quota_guest_within_limit():
    """GUEST users should be allowed for files <= 10MB."""
    actor = "test_guest_valid@truthlens.ai"
    valid_size = 5 * 1024 * 1024  # 5 MB
    allowed, reason, usage = check_user_quota(
        actor_key=actor,
        role="GUEST",
        is_guest=True,
        incoming_bytes=valid_size
    )
    assert allowed, "GUEST should be allowed for files <= 10MB"
    assert reason == "OK"
    assert "file_count" in usage


def test_check_user_quota_standard_file_size():
    """STANDARD users have 25MB file size limit."""
    actor = "test_standard_size@truthlens.ai"
    over_size = 30 * 1024 * 1024  # 30 MB > 25MB limit
    allowed, reason, _ = check_user_quota(
        actor_key=actor,
        role="STANDARD",
        is_guest=False,
        incoming_bytes=over_size
    )
    assert not allowed, "STANDARD should be rejected for files > 25MB"


def test_check_user_quota_verified_file_size():
    """VERIFIED_INVESTIGATOR users have 150MB file size limit."""
    actor = "test_verified_size@truthlens.ai"
    over_size = 200 * 1024 * 1024  # 200 MB > 150MB limit
    allowed, reason, _ = check_user_quota(
        actor_key=actor,
        role="VERIFIED_INVESTIGATOR",
        is_guest=False,
        incoming_bytes=over_size
    )
    assert not allowed, "VERIFIED should be rejected for files > 150MB"


def test_check_user_quota_file_count_guest():
    """GUEST users limited to 3 files max."""
    actor = "test_guest_count@truthlens.ai"
    allowed_next, reason_next, _ = check_user_quota(
        actor_key=actor,
        role="GUEST",
        is_guest=True,
        incoming_bytes=1024,
        extra_files=4
    )
    assert not allowed_next
    assert "limit" in reason_next.lower() or "exceed" in reason_next.lower()


def test_build_quota_status_guest():
    """build_quota_status returns correct usage for GUEST."""
    status = build_quota_status(
        actor_key="test_status_guest@truthlens.ai",
        role="GUEST",
        is_guest=True
    )
    assert status["tier"] == "GUEST"
    assert status["limits"]["max_file_count"] == 3
    assert status["limits"]["max_total_storage_mb"] == 25


def test_build_quota_status_standard():
    """build_quota_status returns correct usage for STANDARD."""
    status = build_quota_status(
        actor_key="test_status_std@truthlens.ai",
        role="STANDARD",
        is_guest=False
    )
    assert status["tier"] == "STANDARD"
    assert status["limits"]["max_file_count"] == 10
    assert status["limits"]["max_total_storage_mb"] == 50


def test_build_quota_status_verified():
    """build_quota_status returns correct usage for VERIFIED_INVESTIGATOR."""
    status = build_quota_status(
        actor_key="test_status_ver@truthlens.ai",
        role="VERIFIED_INVESTIGATOR",
        is_guest=False
    )
    assert status["tier"] == "VERIFIED_INVESTIGATOR"
    assert status["limits"]["max_file_count"] == 50
    assert status["limits"]["max_total_storage_mb"] == 500


def test_quota_tiers_structure():
    """Verify QUOTA_TIERS has correct structure."""
    assert "GUEST" in QUOTA_TIERS
    assert "STANDARD" in QUOTA_TIERS
    assert "VERIFIED_INVESTIGATOR" in QUOTA_TIERS

    guest = QUOTA_TIERS["GUEST"]
    assert guest["max_file_count"] == 3
    assert guest["max_file_size_mb"] == 10
    assert guest["max_total_storage_mb"] == 25

    standard = QUOTA_TIERS["STANDARD"]
    assert standard["max_file_count"] == 10
    assert standard["max_file_size_mb"] == 25
    assert standard["max_total_storage_mb"] == 50

    verified = QUOTA_TIERS["VERIFIED_INVESTIGATOR"]
    assert verified["max_file_count"] == 50
    assert verified["max_file_size_mb"] == 150
    assert verified["max_total_storage_mb"] == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
