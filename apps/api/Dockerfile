# ============================================
# Vision Query API - Dockerfile
# ============================================
FROM python:3.12-slim AS base

# Install system dependencies required by opencv, psycopg, spacy, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy workspace root files needed by uv
COPY pyproject.toml uv.lock ./

# Copy the api package
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/app apps/api/app
COPY apps/api/run_server.py apps/api/run_server.py
COPY apps/api/alembic.ini apps/api/alembic.ini
COPY apps/api/alembic apps/api/alembic

# Copy the ai-pipeline workspace dependency
COPY packages/ai-pipeline/pyproject.toml packages/ai-pipeline/pyproject.toml
COPY packages/ai-pipeline/src packages/ai-pipeline/src
COPY packages/ai-pipeline/detectors packages/ai-pipeline/detectors
COPY packages/ai-pipeline/exporters packages/ai-pipeline/exporters
COPY packages/ai-pipeline/models packages/ai-pipeline/models
COPY packages/ai-pipeline/trackers packages/ai-pipeline/trackers
COPY packages/ai-pipeline/vector_store packages/ai-pipeline/vector_store
COPY packages/ai-pipeline/reports packages/ai-pipeline/reports

# Copy YOLO model weights
COPY packages/ai-pipeline/yolo11m.pt packages/ai-pipeline/yolo11m.pt

# Install dependencies using uv (CPU-only torch to keep image smaller)
RUN uv sync --package api --no-dev --frozen

EXPOSE 8000

# Use uv run to execute within the managed venv
CMD ["uv", "run", "--frozen", "--package", "api", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
