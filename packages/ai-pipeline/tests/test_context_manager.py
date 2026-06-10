"""Tests for the GPU autoclean context manager.

Verifies that the context manager falls back to CPU if CUDA is unavailable
and executes blocks correctly.
"""

import torch
from src.context_manager import gpu_autoclean_context


def test_gpu_autoclean_context_fallback():
    """Verify context manager falls back to CPU or CUDA device cleanly."""
    device_id_val = 0
    with gpu_autoclean_context(device_id=device_id_val) as device:
        assert isinstance(device, torch.device)
        if torch.cuda.is_available():
            assert device.type == "cuda"
        else:
            assert device.type == "cpu"
