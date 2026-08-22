"""
app/core/security_guard.py
==========================
Data Isolation, Path Traversal Defense, and Cryptographic Sanitization.
Ensures zero unauthorized directory access or arbitrary file execution.
"""
import re
import os
from pathlib import Path
from typing import Optional


DANGEROUS_EXTENSIONS = {
    "php", "php3", "php4", "php5", "phtml", "exe", "bat", "cmd", "sh",
    "bash", "zsh", "ps1", "py", "pyc", "pyd", "rb", "pl", "cgi", "jar",
    "jsp", "asp", "aspx", "com", "vbs", "scr", "msi", "dll", "so", "dylib"
}


def sanitize_filename(filename: str) -> str:
    """
    Sanitizes untrusted client-supplied filenames:
    - Strips path traversal sequences (../, ..\)
    - Removes null bytes and control characters
    - Blocks dangerous executable double extensions
    """
    if not filename:
        return "unnamed_evidence"

    # Normalize backslashes and extract base filename
    normalized = filename.replace("\\", "/").replace("\\", "/")
    clean = os.path.basename(normalized)
    
    # Remove null bytes and non-printable characters
    clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", clean)
    
    # Remove dangerous characters
    clean = re.sub(r'[<>:"/\\|?*]', "", clean).strip(". ")

    # Check for dangerous double extensions (e.g. image.jpg.exe)
    parts = clean.lower().split(".")
    if len(parts) > 1 and parts[-1] in DANGEROUS_EXTENSIONS:
        clean = ".".join(parts[:-1]) + ".blocked"

    return clean or "unnamed_evidence"


def validate_safe_path(target_path: Path, allowed_base_dir: Path) -> bool:
    """
    Verifies that target_path strictly resides within allowed_base_dir.
    Prevents path traversal attacks (e.g. ../../etc/passwd or ../storage/evidence_x.db).
    """
    try:
        resolved_target = target_path.resolve()
        resolved_base = allowed_base_dir.resolve()
        return str(resolved_target).startswith(str(resolved_base))
    except Exception:
        return False
