"""Module containing the GPU context manager for safe CUDA operations.

This module provides a context manager to wrap PyTorch GPU operations,
ensuring CUDA memory caches are emptied, streams are synchronized, and
out-of-memory exceptions are handled gracefully.
"""

import logging
import contextlib
import torch

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def gpu_autoclean_context(device_id: int = 0):
    """Context manager for managing PyTorch GPU device operations and cleanup.

    Sets the active CUDA device, synchronizes activities, handles out-of-memory
    exceptions, and empties the GPU cache upon exit.

    Args:
        device_id (int): The index of the GPU device to target. Defaults to 0.

    Yields:
        torch.device: The configured PyTorch device object.

    Raises:
        RuntimeError: Re-raises any non-OOM critical CUDA failures.
    """
    if not torch.cuda.is_available():
        logger.warning("CUDA is not available. Falling back to CPU context.")
        yield torch.device("cpu")
        return

    device = torch.device(f"cuda:{device_id}")
    try:
        # Set active device
        torch.cuda.set_device(device)
        logger.info("Switched to GPU device: %s", device)
        yield device
    except torch.cuda.OutOfMemoryError as oom_err:
        logger.error("CUDA Out of Memory in GPU context: %s", str(oom_err))
        # Empty cache to recover
        torch.cuda.empty_cache()
        raise oom_err
    except Exception as exc:
        logger.error("General error during GPU operation: %s", str(exc))
        raise exc
    finally:
        # Empty the CUDA cache to prevent leakage
        torch.cuda.empty_cache()
        logger.info("Cleared CUDA memory cache for GPU device: %s", device)
