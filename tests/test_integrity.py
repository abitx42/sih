import tempfile
from pathlib import Path
from app.core.integrity_engine import calculate_file_hashes, verify_integrity

def test_hash_calculation():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"TRUTH LENS SECURE CRYPTOGRAPHIC TEST PAYLOAD")
        temp_path = Path(f.name)

    try:
        hashes = calculate_file_hashes(temp_path)
        assert "sha256" in hashes
        assert "sha512" in hashes
        assert "md5" in hashes
        assert len(hashes["sha256"]) == 64
        assert len(hashes["sha512"]) == 128
        assert len(hashes["md5"]) == 32
        
        # Test verification match
        is_valid, current_sha, msg = verify_integrity(temp_path, hashes["sha256"])
        assert is_valid is True
        assert current_sha == hashes["sha256"]

        # Test verification mismatch
        is_valid_bad, _, _ = verify_integrity(temp_path, "0000000000000000000000000000000000000000000000000000000000000000")
        assert is_valid_bad is False
    finally:
        if temp_path.exists():
            temp_path.unlink()
