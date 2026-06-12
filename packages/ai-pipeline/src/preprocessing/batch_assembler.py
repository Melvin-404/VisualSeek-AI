"""Assembles preprocessed frames into pinned-memory batches and tracks pipeline statistics."""

import logging
import time
from typing import Dict, List, Optional, Tuple

import torch

# Try importing pynvml
try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

logger = logging.getLogger(__name__)


class BatchAssembler:
    """Combines preprocessed tensors into batches and tracks processing statistics.

    Maintains a buffer of preprocessed tensors and metadata, creating pinned batches
    when the target batch size (default 32) is reached.
    """

    def __init__(self, batch_size: int = 32, pin_memory: bool = True):
        self.batch_size = batch_size
        self.pin_memory = pin_memory and torch.cuda.is_available()

        # Buffers
        self.tensor_buffer: List[torch.Tensor] = []
        self.metadata_buffer: List[dict] = []

        # Stats tracking
        self.start_time = time.perf_counter()
        self.processed_frames = 0
        self.total_preprocessing_time = 0.0

        # Initialize NVML for GPU statistics if available
        self._nvml_initialized = False
        if NVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self._nvml_initialized = True
                logger.info("NVML initialized successfully for GPU stats tracking.")
            except Exception as e:
                logger.debug("Failed to initialize NVML: %s", e)

    def add_frame(self, preprocessed_tensor: torch.Tensor, metadata: dict) -> None:
        """Add a preprocessed frame and its metadata to the batch buffer."""
        self.tensor_buffer.append(preprocessed_tensor)
        self.metadata_buffer.append(metadata)
        self.processed_frames += 1

    def is_ready(self) -> bool:
        """Check if the buffer has enough frames to form a batch."""
        return len(self.tensor_buffer) >= self.batch_size

    def get_gpu_metrics(self) -> Dict[str, float]:
        """Query NVIDIA GPU metrics via NVML."""
        metrics = {
            "gpu_utilization_pct": 0.0,
            "gpu_memory_used_mb": 0.0,
            "gpu_memory_total_mb": 0.0,
        }

        if self._nvml_initialized:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                
                metrics["gpu_utilization_pct"] = float(util.gpu)
                metrics["gpu_memory_used_mb"] = float(mem.used) / (1024 ** 2)
                metrics["gpu_memory_total_mb"] = float(mem.total) / (1024 ** 2)
            except Exception as e:
                logger.debug("Failed to query NVML device metrics: %s", e)

        return metrics

    def assemble_batch(self) -> Optional[Tuple[torch.Tensor, List[dict], Dict[str, float]]]:
        """Assembles the buffered frames into a single pinned batch.

        Returns:
            A tuple of (batch_tensor, metadata_list, stats_dict) or None if buffer is empty.
        """
        if not self.tensor_buffer:
            return None

        # Determine batch count to slice
        slice_size = min(len(self.tensor_buffer), self.batch_size)
        
        batch_tensors = self.tensor_buffer[:slice_size]
        batch_metadata = self.metadata_buffer[:slice_size]

        # Remove sliced frames from buffers
        self.tensor_buffer = self.tensor_buffer[slice_size:]
        self.metadata_buffer = self.metadata_buffer[slice_size:]

        # Record start time of assembly
        t_start = time.perf_counter()

        # Stack into batch tensor
        batch_tensor = torch.stack(batch_tensors)

        # Pin memory if tensor is on CPU to enable fast asynchronous host-to-device transfers
        if self.pin_memory and batch_tensor.device.type == "cpu":
            batch_tensor = batch_tensor.pin_memory()

        # Track latency
        t_end = time.perf_counter()
        assembly_latency_ms = (t_end - t_start) * 1000

        # Calculate statistics
        elapsed_total = time.perf_counter() - self.start_time
        fps = self.processed_frames / elapsed_total if elapsed_total > 0 else 0.0

        gpu_stats = self.get_gpu_metrics()

        stats = {
            "fps": fps,
            "batch_size": float(slice_size),
            "assembly_latency_ms": assembly_latency_ms,
            "gpu_utilization": gpu_stats["gpu_utilization_pct"],
            "gpu_memory_used_mb": gpu_stats["gpu_memory_used_mb"],
        }

        return batch_tensor, batch_metadata, stats

    def clear(self) -> None:
        """Clear all buffers."""
        self.tensor_buffer.clear()
        self.metadata_buffer.clear()

    def __del__(self):
        """Shutdown NVML context on object destruction."""
        if self._nvml_initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
