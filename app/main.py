import os
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings, BASE_DIR
from app.database import init_db, reconcile_orphaned_jobs
from app.api.routes_cases import router as cases_router
from app.api.routes_evidence import router as evidence_router
from app.api.routes_custody import router as custody_router
from app.api.routes_copilot import router as copilot_router
from app.api.routes_reports import router as reports_router
from app.api.routes_dashboard import router as dashboard_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("evidence_x")

# Initialize SQLite database schema
init_db()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Digital Evidence Forensic Assessment Platform — SIH PS-27",
    version=settings.VERSION
)

@app.on_event("startup")
def startup_event():
    recovered = reconcile_orphaned_jobs()
    if recovered > 0:
        logger.info(f"Startup recovery: Reconciled {recovered} orphaned analysis job(s) left in ANALYZING state.")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(dashboard_router)
app.include_router(cases_router)
app.include_router(evidence_router)
app.include_router(custody_router)
app.include_router(copilot_router)
app.include_router(reports_router)

# Mount Static Files (Web UI)
STATIC_DIR = Path(__file__).resolve().parent / "static"
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "EVIDENCE-X Backend API is active. Web UI initializing."}

@app.get("/api/health")
def health_check():
    return {
        "status": "HEALTHY",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "ps_number": settings.PS_NUMBER
    }
