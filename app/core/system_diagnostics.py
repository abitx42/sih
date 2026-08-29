"""
app/core/system_diagnostics.py
==============================
Production System Health, Hardware Acceleration Diagnostics, and Storage Telemetry.
"""
from __future__ import annotations

import os
import sys
import time
import shutil
import logging
from pathlib import Path
from typing import Dict, Any

from app.config import settings, EVIDENCE_DIR, FORENSIC_DIR, REPORTS_DIR, STORAGE_DIR, DB_PATH
from app.database import get_db

logger = logging.getLogger(__name__)

_START_TIME = time.time()


class SystemDiagnostics:
    """Provides comprehensive health and diagnostic metrics for the forensic server."""

    @staticmethod
    def get_system_health() -> Dict[str, Any]:
        """Runs fast non-blocking health checks across DB, filesystem, and runtime."""
        # 1. Database Health & Latency
        db_status = "HEALTHY"
        db_latency_ms = 0.0
        db_wal_mode = False
        try:
            t0 = time.perf_counter()
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.execute("PRAGMA journal_mode")
                row = cursor.fetchone()
                if row:
                    val = str(row[0] if isinstance(row, (tuple, list)) else (row["journal_mode"] if "journal_mode" in row.keys() else list(row)[0]))
                    if "wal" in val.lower():
                        db_wal_mode = True
            db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            db_status = "DEGRADED"

        # 2. Storage Directories & Disk Availability
        storage_status = "HEALTHY"
        try:
            for p in (EVIDENCE_DIR, FORENSIC_DIR, REPORTS_DIR, STORAGE_DIR):
                p.mkdir(parents=True, exist_ok=True)
            disk_usage = shutil.disk_usage(str(STORAGE_DIR))
            free_gb = round(disk_usage.free / (1024 ** 3), 2)
            total_gb = round(disk_usage.total / (1024 ** 3), 2)
        except Exception as e:
            logger.error(f"Storage check failed: {e}")
            storage_status = "DEGRADED"
            free_gb = 0.0
            total_gb = 0.0

        # 3. Hardware Compute Detection
        device_type = "CPU"
        gpu_name = None
        try:
            import torch
            if torch.cuda.is_available():
                device_type = "CUDA GPU"
                gpu_name = torch.cuda.get_device_name(0)
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device_type = "Apple Silicon MPS"
                gpu_name = "Apple Neural Engine / Metal"
        except Exception:
            pass

        # 4. Multi-Tier Gateway Status
        gateways = {
            "aadicombo_gateway": bool(getattr(settings, "AADICOMBO_API_KEY", "")),
            "omniroute_gateway": bool(getattr(settings, "OMNIROUTE_API_KEY", "")),
            "google_cloud_vision": bool(getattr(settings, "GOOGLE_CLOUD_VISION_KEY", "")),
            "sightengine_gateway": bool(getattr(settings, "SIGHTENGINE_API_USER", "") and getattr(settings, "SIGHTENGINE_API_SECRET", "")),
            "groq_gateway": bool(os.getenv("GROQ_API_KEY", "")),
            "serp_api": bool(getattr(settings, "SERP_API_KEY", ""))
        }

        overall_status = "HEALTHY" if (db_status == "HEALTHY" and storage_status == "HEALTHY") else "DEGRADED"
        uptime_sec = round(time.time() - _START_TIME, 1)

        return {
            "status": overall_status,
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "ps_number": settings.PS_NUMBER,
            "uptime_seconds": uptime_sec,
            "environment": {
                "python_version": sys.version.split()[0],
                "platform": sys.platform,
                "compute_device": device_type,
                "gpu_device": gpu_name
            },
            "database": {
                "status": db_status,
                "latency_ms": db_latency_ms,
                "wal_mode": db_wal_mode,
                "engine": "SQLite WAL"
            },
            "storage": {
                "status": storage_status,
                "free_disk_gb": free_gb,
                "total_disk_gb": total_gb
            },
            "configured_gateways": gateways
        }
