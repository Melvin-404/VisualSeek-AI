# Vision Query AI Monorepo

Welcome to the **Vision Query AI** monorepo. This repository contains the Next.js frontend, FastAPI backend, and PyTorch ML pipelines, built to enterprise-grade standards with GPU-accelerated computing capabilities.

---

## 🏗️ Architecture Overview

The codebase is organized as a Turborepo monorepo powered by `pnpm` and `python` workspaces:

```
visionquery-ai/
├── apps/
│   ├── web/          # Next.js 15 frontend
│   └── api/          # FastAPI backend (python)
├── packages/
│   ├── ai-pipeline/  # Python ML pipeline (pytorch)
│   ├── shared-types/ # TypeScript types
│   └── ui/           # Shared Component library
├── infra/
│   ├── k8s/          # Kubernetes manifests
│   ├── helm/         # Helm charts
│   └── terraform/    # Infrastructure as Code (IaC)
├── scripts/          # Dev utility and validation scripts
└── docs/             # Technical architecture and API documentation
```

---

## ⚡ Prerequisites

To run this monorepo locally, ensure your machine meets the following version requirements:

- **Operating System**: Windows 11 with WSL2 (recommended) or Linux (Ubuntu 22.04 LTS+)
- **Node.js**: v20 LTS (or higher)
- **pnpm**: v11 (or higher)
- **Python**: v3.12 (or higher)
- **Docker**: Docker Engine 29+ & Docker Compose v2 with GPU support
- **NVIDIA GPU**: RTX 30/40 series (local dev) or H100/H200 (production CI runner)
- **NVIDIA Container Toolkit**: Installed and configured for Docker GPU passthrough

---

## 🚀 Local Development Setup

### 1. Clone & Set Up Environment
Copy the example environments:
```bash
cp apps/web/.env.example apps/web/.env
cp apps/api/.env.example apps/api/.env
```

### 2. Install Node Dependencies
```bash
pnpm install
```

### 3. Install Python Dependencies
For local Python virtual environments, create a venv in the packages or apps directories:
```bash
# apps/api
cd apps/api
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# packages/ai-pipeline
cd ../../packages/ai-pipeline
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Running the Dev Server
To start all services concurrently (frontend + backend):
```bash
pnpm dev
```

---

## 🏎️ GPU / CUDA Requirements & Health Check

Production workloads require an **NVIDIA H200 GPU** runner labeled `nvidia-h200` in GitHub Actions. For local testing, any CUDA-compatible GPU is supported.

### GPU Verification Script
We provide a validation script that checks CUDA availability, VRAM size, and compute capabilities:
```bash
python scripts/gpu_healthcheck.py
```
This script will:
- Check for standard NVIDIA device drivers.
- Assert CUDA availability.
- Print warnings if your GPU is lower-spec than the enterprise H200 (e.g. RTX 4060), but exit `0` to allow local development. It will strictly exit `1` on failure in production/CI systems.

### Docker GPU Passthrough
To run Python/ML operations inside containers with GPU acceleration, ensure you start the services with Docker Compose:
```bash
docker compose up --build
```
This maps the host GPU into the FastAPI backend and AI pipeline containers using the `nvidia` driver reservations.

---

## 🔒 Security & Code Quality

### Git Hooks & Conventional Commits
This project enforces conventional commits using `commitlint` and standardizes styling using `pre-commit` hooks.
Install hooks:
```bash
pnpm prepare
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

### GPG Signed Commits
All commits to the `visionquery-ai` repository **must** be GPG-signed.
To configure GPG signing locally:
1. Generate a GPG key: `gpg --full-generate-key`
2. Add your GPG key to your GitHub account.
3. Configure git to sign your commits:
   ```bash
   git config --global user.signingkey <YOUR_KEY_ID>
   git config --global commit.gpgsign true
   ```
