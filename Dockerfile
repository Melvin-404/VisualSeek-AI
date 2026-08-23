# ============================================
# Vision Query Combined - Dockerfile
# ============================================
FROM python:3.12-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22.x
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pnpm@11.3.0

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# --- Copy Workspace Metadata ---
COPY pyproject.toml uv.lock ./
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./

# --- Copy Source Code First (Ensures correct pnpm and uv workspace linking) ---
COPY packages/shared-types ./packages/shared-types
COPY packages/ui ./packages/ui
COPY packages/ai-pipeline ./packages/ai-pipeline

COPY apps/web ./apps/web
COPY apps/api ./apps/api

# --- Run Dependency Installations ---
RUN uv sync --package api --no-dev --frozen
RUN pnpm install --frozen-lockfile

# Copy startup script
COPY start.sh ./
RUN chmod +x start.sh

# Environment settings
ENV NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_APP_ENV=development
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
ENV API_ENV=development

EXPOSE 3000 8000

CMD ["./start.sh"]
