# Truth Lens — Production Container Image
FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

WORKDIR /app

# Install system runtime dependencies for OpenCV and Media Forensics
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create application user and storage directories
RUN useradd -m -u 1000 truthlens && \
    mkdir -p /app/storage/evidence /app/storage/forensic /app/storage/reports /app/storage/thumbnails /app/storage/models && \
    chown -R truthlens:truthlens /app

# Copy application source code
COPY . .
RUN chown -R truthlens:truthlens /app

USER truthlens

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
