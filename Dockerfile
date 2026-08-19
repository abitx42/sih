# Truth Lens — Digital Evidence Forensics Platform (SIH PS-27)
# Production Container Image for Oracle Cloud Always Free VM

FROM python:3.9-slim

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    STORAGE_DIR=/app/storage

# Install essential system packages for OpenCV, libmagic, FFmpeg audio decoding, and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and helper scripts
COPY app/ ./app/
COPY scripts/ ./scripts/

# Create persistent storage mount directory tree
RUN mkdir -p /app/storage/evidence \
             /app/storage/forensic \
             /app/storage/reports \
             /app/storage/models

# Container Healthcheck (Lightweight endpoint; does not load ML model or reveal secrets)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://127.0.0.1:${PORT:-8000}/health || exit 1

# Expose internal application port
EXPOSE 8000

# Run FastAPI with single worker (required by SQLite & in-process BackgroundTasks)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
