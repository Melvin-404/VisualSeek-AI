FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY packages/ai-pipeline/pyproject.toml ./
RUN pip3 install torch --index-url https://download.pytorch.org/whl/cu121
RUN pip3 install .
COPY packages/ai-pipeline/src ./src
CMD ["python3", "-c", "import torch; print('CUDA active:', torch.cuda.is_available())"]
