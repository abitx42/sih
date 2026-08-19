import pytest
import zipfile
import tempfile
from pathlib import Path
from fastapi import HTTPException
from app.security.validator import sanitize_filename, detect_mime_and_modality, validate_archive_security

def test_filename_sanitization():
    bad_name = "../../etc/passwd\x00malicious.jpg"
    clean = sanitize_filename(bad_name)
    assert ".." not in clean
    assert "/" not in clean
    assert "\\" not in clean
    assert "\x00" not in clean

def test_zip_slip_rejection():
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
        zip_path = Path(f.name)

    try:
        with zipfile.ZipFile(zip_path, 'w') as zf:
            # Add a malicious entry with path traversal
            zf.writestr("../../malicious.sh", b"echo 'hack'")

        with pytest.raises(HTTPException) as excinfo:
            validate_archive_security(zip_path)
        assert "Zip Slip" in str(excinfo.value.detail)
    finally:
        if zip_path.exists():
            zip_path.unlink()
