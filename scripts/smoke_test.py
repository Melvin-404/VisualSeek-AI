"""Smoke-test script for Vision Query development environment.

Validates that Python version, Node version, Docker daemon access, and GPU/CUDA
availability meet the minimum development requirements.
"""

import sys
import subprocess

# Reconfigure stdout to use UTF-8 on Windows to prevent UnicodeEncodeError with emojis
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

MIN_PYTHON_MAJOR = 3
MIN_PYTHON_MINOR = 12
MIN_NODE_VERSION = 20
EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def check_python_version() -> bool:
    """Validates the current Python interpreter version.

    Returns:
        bool: True if Python version meets requirements, False otherwise.
    """
    major, minor = sys.version_info.major, sys.version_info.minor
    print(f"Checking Python version... Found: {major}.{minor}")
    if major < MIN_PYTHON_MAJOR or (major == MIN_PYTHON_MAJOR and minor < MIN_PYTHON_MINOR):
        print(f"❌ Python version must be >= {MIN_PYTHON_MAJOR}.{MIN_PYTHON_MINOR}")
        return False
    print("✅ Python version OK")
    return True


def check_node_version() -> bool:
    """Validates that Node.js is installed and meets version requirements.

    Returns:
        bool: True if Node.js is available and >= MIN_NODE_VERSION, False otherwise.
    """
    print("Checking Node.js version...")
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, check=True)
        raw_version = result.stdout.strip().lstrip("v")
        major = int(raw_version.split(".")[0])
        print(f"Found Node.js: v{raw_version}")
        if major < MIN_NODE_VERSION:
            print(f"❌ Node.js version must be >= v{MIN_NODE_VERSION}")
            return False
        print("✅ Node.js version OK")
        return True
    except (FileNotFoundError, subprocess.SubprocessError, ValueError) as err:
        print(f"❌ Failed to verify Node.js: {err}")
        return False


def check_docker_access() -> bool:
    """Validates Docker daemon access.

    Returns:
        bool: True if Docker daemon is accessible, False otherwise.
    """
    print("Checking Docker daemon access...")
    try:
        subprocess.run(["docker", "ps"], capture_output=True, text=True, check=True)
        print("✅ Docker daemon access OK")
        return True
    except (FileNotFoundError, subprocess.SubprocessError) as err:
        print(f"❌ Docker daemon is not accessible: {err}")
        return False


def check_gpu_availability() -> bool:
    """Validates NVIDIA GPU availability.

    Returns:
        bool: True if GPU is available, False otherwise.
    """
    print("Checking NVIDIA GPU availability...")
    try:
        subprocess.run(["nvidia-smi"], capture_output=True, text=True, check=True)
        print("✅ NVIDIA GPU/CUDA availability OK")
        return True
    except (FileNotFoundError, subprocess.SubprocessError) as err:
        print(f"❌ NVIDIA GPU/CUDA is not available: {err}")
        return False


def run_smoke_test():
    """Runs all smoke tests to validate the environment."""
    print("🚀 Starting environment smoke-test...")
    tests = [
        ("Python Version", check_python_version),
        ("Node Version", check_node_version),
        ("Docker Daemon", check_docker_access),
        ("NVIDIA GPU", check_gpu_availability),
    ]

    all_passed = True
    for name, test_func in tests:
        print("-" * 40)
        if not test_func():
            print(f"❌ Test failed: {name}")
            all_passed = False

    print("=" * 40)
    if all_passed:
        print("🎉 All environment verification tests passed!")
        sys.exit(EXIT_SUCCESS)
    else:
        print("❌ Some environment verification tests failed.")
        sys.exit(EXIT_FAILURE)


if __name__ == "__main__":
    run_smoke_test()
