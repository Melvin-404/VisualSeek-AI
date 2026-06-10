"""NVIDIA GPU and CUDA Runtime Health-Check Script.

This script validates CUDA availability, GPU memory capacity, compute capability,
and verifies compatibility with target NVIDIA H200 specifications. It permits
local developer environments with lower specs to pass with warnings, while
enforcing strict H200 requirements in the CI pipeline.
"""

import os
import subprocess
import sys

# Reconfigure stdout to use UTF-8 on Windows to prevent UnicodeEncodeError with emojis
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

# Define configuration constants to avoid magic numbers
REQUIRED_H200_COMPUTE_CAP = 9.0
REQUIRED_H200_MEMORY_MB = 140000  # 141 GB H200 Memory
EXIT_CODE_SUCCESS = 0
EXIT_CODE_FAILURE = 1


def run_nvidia_smi() -> str:
    """Executes the nvidia-smi query to fetch GPU hardware metrics.

    Returns:
        str: Comma-separated query output containing name, memory, and compute.

    Raises:
        FileNotFoundError: If nvidia-smi command is not available.
        subprocess.SubprocessError: If execution fails.
    """
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,compute_cap",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def check_gpu_health() -> int:
    """Validates GPU availability and hardware compliance.

    Checks if an NVIDIA GPU is present, parses memory and compute capability,
    and validates them against H200 requirements.

    Returns:
        int: Exit status code (0 for success, 1 for failure).
    """
    print("🔍 Initializing NVIDIA H200 GPU Health Check...")

    # 1. Check if nvidia-smi is available
    try:
        query_out = run_nvidia_smi()
    except (FileNotFoundError, subprocess.SubprocessError) as err:
        print(f"❌ Error executing nvidia-smi: {err}")
        print("Please verify that the NVIDIA drivers and CUDA are installed.")
        return EXIT_CODE_FAILURE

    if not query_out:
        print("❌ No GPU devices found or query output is empty.")
        return EXIT_CODE_FAILURE

    # 2. Parse query results (support multi-GPU setup by checking first device)
    gpu_lines = query_out.split("\n")
    gpu_info = [part.strip() for part in gpu_lines[0].split(",")]

    if len(gpu_info) < 3:
        print(f"❌ Unexpected nvidia-smi query format: {query_out}")
        return EXIT_CODE_FAILURE

    gpu_name = gpu_info[0]
    try:
        gpu_memory_mb = float(gpu_info[1])
        gpu_compute_cap = float(gpu_info[2])
    except ValueError as val_err:
        print(f"❌ Error parsing GPU metrics: {val_err}")
        return EXIT_CODE_FAILURE

    print(f"✅ Found GPU: {gpu_name}")
    print(f"   - Total VRAM: {gpu_memory_mb:.1f} MB")
    print(f"   - Compute Capability: {gpu_compute_cap:.1f}")

    is_ci = os.environ.get("CI", "false").lower() == "true"
    is_h200 = "H200" in gpu_name or (
        gpu_memory_mb >= REQUIRED_H200_MEMORY_MB
        and gpu_compute_cap >= REQUIRED_H200_COMPUTE_CAP
    )

    # 3. Environment Specific Assertions
    if is_ci:
        print("🖥️ Running in CI environment. Enforcing strict H200 validation...")
        if not is_h200:
            print(
                f"❌ Hardware compliance check failed for H200.\n"
                f"   Required VRAM: >= {REQUIRED_H200_MEMORY_MB} MB (Found: {gpu_memory_mb:.1f} MB)\n"
                f"   Required Compute: >= {REQUIRED_H200_COMPUTE_CAP} (Found: {gpu_compute_cap:.1f})"
            )
            return EXIT_CODE_FAILURE
        print("🎉 GPU Compliance Validation Passed successfully!")
    else:
        print("💻 Running in Local environment.")
        if not is_h200:
            print(
                f"⚠️  Warning: Local GPU '{gpu_name}' does not meet enterprise H200 specifications.\n"
                f"   This is acceptable for local development. Continuing..."
            )
        else:
            print("🚀 Local machine meets H200 requirements!")

    # 4. Torch CUDA check if torch is importable
    try:
        import torch

        cuda_available = torch.cuda.is_available()
        print(f"✅ PyTorch CUDA availability: {cuda_available}")
        if cuda_available:
            print(f"   - Device Count: {torch.cuda.device_count()}")
            print(f"   - Current Device: {torch.cuda.current_device()}")
            print(
                f"   - Device Name: {torch.cuda.get_device_name(torch.cuda.current_device())}"
            )
        else:
            if is_ci:
                print("❌ PyTorch reports CUDA is NOT available in CI environment.")
                return EXIT_CODE_FAILURE
            print("⚠️  PyTorch reports CUDA is not available. Check your PyTorch wheel version.")
    except ImportError:
        print("💡 PyTorch not installed in this environment; skipping PyTorch validation.")

    return EXIT_CODE_SUCCESS


if __name__ == "__main__":
    sys.exit(check_gpu_health())
