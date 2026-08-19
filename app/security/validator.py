import os
import re
import zipfile
import tarfile
from pathlib import Path
from typing import Tuple, Optional
from fastapi import HTTPException

# Magic Byte Signatures
MAGIC_SIGNATURES = {
    "image/jpeg": [b"\xFF\xD8\xFF"],
    "image/png": [b"\x89\x50\x4E\x47\x0D\x0A\x1A\x0A"],
    "image/webp": [b"RIFF"],  # Followed by WEBP at offset 8
    "image/bmp": [b"BM"],
    "image/tiff": [b"II\x2A\x00", b"MM\x00\x2A"],
    "video/mp4": [b"ftyp", b"moov", b"mdat"],  # typically at offset 4 or 0
    "video/x-msvideo": [b"RIFF"],  # Followed by AVI at offset 8
    "video/quicktime": [b"ftypqt", b"moov", b"wide", b"mdat"],
    "video/webm": [b"\x1A\x45\xDF\xA3"],
    "audio/wav": [b"RIFF"],  # Followed by WAVE at offset 8
    "audio/mpeg": [b"\xFF\xFB", b"\xFF\xF3", b"\xFF\xF2", b"ID3"],
    "audio/ogg": [b"OggS"],
    "application/pdf": [b"%PDF-"],
    "application/zip": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    "application/gzip": [b"\x1F\x8B"],
    "application/x-tar": [b"ustar"],  # at offset 257
    "application/vnd.openxmlformats-officedocument": [b"PK\x03\x04"],  # DOCX/XLSX/PPTX
}

def sanitize_filename(filename: str) -> str:
    """
    Sanitize uploaded filename to prevent Path Traversal, Null Byte injection,
    and forbidden OS characters.
    """
    # Remove directory paths
    filename = os.path.basename(filename)
    # Strip null bytes and control chars
    filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
    # Remove any traversal patterns
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")
    # Keep only safe alphanumeric, dots, underscores, dashes
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    if not filename or filename == ".":
        filename = "unnamed_evidence.bin"
    return filename

def detect_mime_and_modality(file_path: Path, filename: str) -> Tuple[str, str]:
    """
    Detects true MIME type and high-level modality using Magic Bytes and file headers.
    Returns (mime_type, modality) where modality is in [IMAGE, VIDEO, AUDIO, DOCUMENT, ARCHIVE, UNKNOWN].
    """
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    
    with open(file_path, "rb") as f:
        header = f.read(512)

    # 1. Image checks
    if header.startswith(b"\xFF\xD8\xFF"):
        return "image/jpeg", "IMAGE"
    if header.startswith(b"\x89\x50\x4E\x47\x0D\x0A\x1A\x0A"):
        return "image/png", "IMAGE"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image/webp", "IMAGE"
    if header.startswith(b"BM"):
        return "image/bmp", "IMAGE"
    if header.startswith(b"II\x2A\x00") or header.startswith(b"MM\x00\x2A"):
        return "image/tiff", "IMAGE"

    # 2. PDF & Documents
    if header.startswith(b"%PDF-"):
        return "application/pdf", "DOCUMENT"

    # 3. Audio checks
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WAVE":
        return "audio/wav", "AUDIO"
    if header.startswith(b"ID3") or header.startswith(b"\xFF\xFB") or header.startswith(b"\xFF\xF3"):
        return "audio/mpeg", "AUDIO"
    if header.startswith(b"OggS"):
        return "audio/ogg", "AUDIO"

    # 4. Video checks
    if b"ftyp" in header[:32] or b"moov" in header[:32] or header.startswith(b"\x1A\x45\xDF\xA3"):
        if ext in ["webm", "mkv"]:
            return "video/webm", "VIDEO"
        return "video/mp4", "VIDEO"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"AVI ":
        return "video/x-msvideo", "VIDEO"

    # 5. Zip / Office OpenXML / Archives
    if header.startswith(b"PK\x03\x04"):
        if ext in ["docx", "doc"]:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "DOCUMENT"
        if ext in ["xlsx", "xls"]:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "DOCUMENT"
        if ext in ["pptx", "ppt"]:
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation", "DOCUMENT"
        return "application/zip", "ARCHIVE"
    
    if header.startswith(b"\x1F\x8B"):
        return "application/gzip", "ARCHIVE"

    # Fallback to extension matching if standard
    ext_mapping = {
        "jpg": ("image/jpeg", "IMAGE"),
        "jpeg": ("image/jpeg", "IMAGE"),
        "png": ("image/png", "IMAGE"),
        "webp": ("image/webp", "IMAGE"),
        "mp4": ("video/mp4", "VIDEO"),
        "avi": ("video/x-msvideo", "VIDEO"),
        "mov": ("video/quicktime", "VIDEO"),
        "mkv": ("video/x-matroska", "VIDEO"),
        "wav": ("audio/wav", "AUDIO"),
        "mp3": ("audio/mpeg", "AUDIO"),
        "pdf": ("application/pdf", "DOCUMENT"),
        "txt": ("text/plain", "DOCUMENT"),
        "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "DOCUMENT"),
        "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "DOCUMENT"),
        "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "DOCUMENT"),
        "zip": ("application/zip", "ARCHIVE"),
        "tar": ("application/x-tar", "ARCHIVE"),
        "gz": ("application/gzip", "ARCHIVE"),
    }
    
    if ext in ext_mapping:
        return ext_mapping[ext]

    return "application/octet-stream", "DOCUMENT"

def validate_archive_security(archive_path: Path, max_uncompressed_bytes: int = 200 * 1024 * 1024) -> None:
    """
    Guards against Zip Slip (Path Traversal) and Zip Bombs.
    Raises HTTPException if malicious structure is detected.
    """
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, 'r') as zf:
            total_size = 0
            for member in zf.infolist():
                # Path traversal check
                target_path = os.path.normpath(member.filename)
                if target_path.startswith("..") or target_path.startswith("/") or target_path.startswith("\\"):
                    raise HTTPException(status_code=400, detail=f"Security Alert: Zip Slip path traversal attempt detected in '{member.filename}'")
                
                total_size += member.file_size
                if total_size > max_uncompressed_bytes:
                    raise HTTPException(status_code=400, detail="Security Alert: Zip Bomb threshold exceeded (>200MB decompressed).")
    
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, 'r:*') as tf:
            total_size = 0
            for member in tf.getmembers():
                target_path = os.path.normpath(member.name)
                if target_path.startswith("..") or target_path.startswith("/") or target_path.startswith("\\"):
                    raise HTTPException(status_code=400, detail=f"Security Alert: Tar path traversal attempt detected in '{member.name}'")
                total_size += member.size
                if total_size > max_uncompressed_bytes:
                    raise HTTPException(status_code=400, detail="Security Alert: Archive bomb threshold exceeded.")
