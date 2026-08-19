import hashlib
from pathlib import Path
from typing import Dict, Tuple

CHUNK_SIZE = 64 * 1024  # 64 KB

def calculate_file_hashes(file_path: Path) -> Dict[str, str]:
    """
    Computes SHA-256, SHA-512, and MD5 cryptographic hashes
    in a memory-efficient chunked stream.
    """
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()
    md5 = hashlib.md5()

    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha256.update(chunk)
            sha512.update(chunk)
            md5.update(chunk)

    return {
        "sha256": sha256.hexdigest(),
        "sha512": sha512.hexdigest(),
        "md5": md5.hexdigest(),
    }

def verify_integrity(file_path: Path, expected_sha256: str) -> Tuple[bool, str, str]:
    """
    Re-computes the current SHA-256 hash of the evidence file on disk and
    compares it against the reference recorded SHA-256 hash.
    
    Returns: (is_valid, current_sha256, status_message)
    """
    if not file_path.exists():
        return False, "", "Evidence file missing on filesystem."

    current_hashes = calculate_file_hashes(file_path)
    current_sha256 = current_hashes["sha256"]

    if current_sha256.lower() == expected_sha256.lower():
        return True, current_sha256, "Cryptographic hash matches recorded baseline. Bit-level integrity preserved."
    else:
        return False, current_sha256, "INTEGRITY MISMATCH: File contents have been modified or corrupted since baseline recording."
