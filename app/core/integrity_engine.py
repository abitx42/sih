import hashlib
import hmac
from pathlib import Path
from typing import Dict, Tuple, Union, Optional

CHUNK_SIZE = 64 * 1024  # 64 KB

def calculate_file_hashes(file_path: Union[Path, str]) -> Dict[str, str]:
    """
    Computes SHA-256, SHA-512, and MD5 cryptographic hashes
    in a memory-efficient chunked stream.
    """
    path_obj = Path(file_path)
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()
    md5 = hashlib.md5()

    with open(path_obj, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha256.update(chunk)
            sha512.update(chunk)
            md5.update(chunk)

    return {
        "sha256": sha256.hexdigest(),
        "sha512": sha512.hexdigest(),
        "md5": md5.hexdigest(),
    }

def verify_integrity(file_path: Union[Path, str], expected_sha256: Optional[str]) -> Tuple[bool, str, str]:
    """
    Re-computes the current SHA-256 hash of the evidence file on disk and
    compares it against the reference recorded SHA-256 hash using constant-time comparison.
    
    Returns: (is_valid, current_sha256, status_message)
    """
    path_obj = Path(file_path)
    if not path_obj.exists() or not path_obj.is_file():
        return False, "", "Evidence file missing on filesystem."

    if not expected_sha256:
        return False, "", "Expected baseline hash not provided."

    current_hashes = calculate_file_hashes(path_obj)
    current_sha256 = current_hashes["sha256"]

    if hmac.compare_digest(current_sha256.lower(), expected_sha256.lower()):
        return True, current_sha256, "Cryptographic hash matches recorded baseline. Bit-level integrity preserved."
    else:
        return False, current_sha256, "INTEGRITY MISMATCH: File contents have been modified or corrupted since baseline recording."
