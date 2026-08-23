# VisualSeek AI

## Overview
VisualSeek AI is an AI-powered intelligent surveillance system that allows users to search surveillance video using natural-language queries.

## Main Technologies
- YOLO11
- PyTorch
- CUDA
- OpenCV
- FastAPI
- Next.js
- PostgreSQL (with pgvector)
- Milvus
- Kubernetes
- JupyterLab

## Features
- CCTV/video analysis
- Object detection
- Natural-language video search
- Semantic search
- Video/frame analysis
- Search results
- Surveillance dashboard

## Project Structure
- `apps/web/`: Next.js frontend application.
- `apps/api/`: FastAPI backend application.
- `packages/ai-pipeline/`: Core AI pipeline including detection, embeddings, and search coordination.
- `infra/`: Infrastructure and configuration.
- `docs/`: Project documentation and presentation materials.

## Setup
To install dependencies and run the project:

```bash
# Install dependencies
pnpm install

# Start development servers
pnpm run dev
```

## Environment Configuration
Sensitive environment variables are not included in this repository. 
Copy `.env.example` to `.env` (or `.env.local` for the web app) and populate it with the appropriate values.

## Presentation
The internship presentation is located at `docs/CSE7000-Internship_PPT_Melvin.pptx` (Note: Currently not present in the workspace but the directory is set up).
