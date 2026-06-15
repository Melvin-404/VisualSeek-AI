#!/usr/bin/env python3
"""GPU resource guard for NVIDIA RTX 4060 Laptop (8 GB VRAM).

Provides:
- ``GPUGuard`` — async-compatible context manager that checks available VRAM
  before entering and logs usage on entry/exit.
- ``get_gpu_status()`` — returns current VRAM usage, total VRAM, temperature.
- ``log_gpu_snapshot()`` — one-shot structured log of GPU metrics for periodic
  monitoring.

Requires ``pynvml`` (``pip install nvidia-ml-py``).

Usage as a context manager::

    with GPUGuard(max_vram_mb=7500):
        # run GPU-intensive work
        ...

Usage as a CLI::

    python packages/ai-pipeline/src/gpu_guard.py
    python packages/ai-pipeline/src/gpu_guard.py --device 0 --budget 7500
"""

from __future__ import annotations

import argparse
import atexit
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger("gpu.guard")

# ---------------------------------------------------------------------------
# NVML lifecycle
# ---------------------------------------------------------------------------

_nvml_initialized: bool = False


def _ensure_nvml() -> None:
    """Lazily initialize NVML (safe to call multiple times)."""
    global _nvml_initialized
    if _nvml_initialized:
        return
    try:
        import pynvml

        pynvml.nvmlInit()
        _nvml_initialized = True
        atexit.register(_shutdown_nvml)
    except Exception as exc:
        raise RuntimeError(
            "Failed to initialize NVML. Is an NVIDIA GPU present and the "
            "nvidia-ml-py package installed? (`pip install nvidia-ml-py`)"
        ) from exc


def _shutdown_nvml() -> None:
    """Clean shutdown of NVML at process exit."""
    global _nvml_initialized
    if _nvml_initialized:
        try:
            import pynvml

            pynvml.nvmlShutdown()
        except Exception:
            pass
        _nvml_initialized = False


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GPUStatus:
    """Snapshot of GPU state."""

    device_index: int
    name: str
    total_vram_mb: float
    used_vram_mb: float
    free_vram_mb: float
    utilization_pct: float
    temperature_c: int
    power_draw_w: Optional[float] = None

    @property
    def used_pct(self) -> float:
        return (self.used_vram_mb / self.total_vram_mb * 100) if self.total_vram_mb else 0.0

    def __str__(self) -> str:
        return (
            f"GPU {self.device_index} ({self.name}): "
            f"{self.used_vram_mb:.0f}/{self.total_vram_mb:.0f} MB VRAM "
            f"({self.used_pct:.1f}% used), "
            f"{self.temperature_c}°C, "
            f"util {self.utilization_pct:.0f}%"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_gpu_status(device_index: int = 0) -> GPUStatus:
    """Return current GPU metrics for the given device.

    Args:
        device_index: CUDA device ordinal (default 0).

    Returns:
        A ``GPUStatus`` dataclass with VRAM, temperature, and utilization.

    Raises:
        RuntimeError: If NVML cannot be initialized or the device is invalid.
    """
    import pynvml

    _ensure_nvml()

    handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
    name_raw = pynvml.nvmlDeviceGetName(handle)
    name = name_raw.decode("utf-8") if isinstance(name_raw, bytes) else str(name_raw)
    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)

    power: Optional[float] = None
    try:
        power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
        power = power_mw / 1000.0
    except pynvml.NVMLError:
        pass

    return GPUStatus(
        device_index=device_index,
        name=name,
        total_vram_mb=mem_info.total / (1024 * 1024),
        used_vram_mb=mem_info.used / (1024 * 1024),
        free_vram_mb=mem_info.free / (1024 * 1024),
        utilization_pct=float(util.gpu),
        temperature_c=int(temp),
        power_draw_w=power,
    )


def log_gpu_snapshot(device_index: int = 0) -> GPUStatus:
    """Log a structured GPU status snapshot and return the status.

    Useful for periodic monitoring (e.g., calling from a timer or health check).
    """
    status = get_gpu_status(device_index)
    logger.info(
        "GPU snapshot",
        device=status.device_index,
        name=status.name,
        used_mb=round(status.used_vram_mb),
        free_mb=round(status.free_vram_mb),
        total_mb=round(status.total_vram_mb),
        used_pct=round(status.used_pct, 1),
        temperature_c=status.temperature_c,
        utilization_pct=status.utilization_pct,
        power_w=round(status.power_draw_w, 1) if status.power_draw_w else None,
    )
    return status


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class GPUGuard:
    """Context manager that enforces a VRAM budget on an NVIDIA GPU.

    Checks available VRAM before entering.  If the *currently used* VRAM
    already exceeds ``max_vram_mb``, raises ``RuntimeError`` to prevent
    OOM during inference.  Logs VRAM on both entry and exit for observability.

    Args:
        max_vram_mb: Maximum allowed VRAM usage in MB (default: 7500 for
            RTX 4060 Laptop with 8 GB).
        device_index: CUDA device ordinal (default 0).

    Example::

        with GPUGuard(max_vram_mb=7500):
            model.predict(frame)
    """

    def __init__(
        self,
        max_vram_mb: float = 7500,
        device_index: int = 0,
    ) -> None:
        self.max_vram_mb = max_vram_mb
        self.device_index = device_index
        self._entry_status: Optional[GPUStatus] = None

    def __enter__(self) -> "GPUGuard":
        status = get_gpu_status(self.device_index)
        self._entry_status = status

        logger.info(
            "GPUGuard: entering",
            used_mb=round(status.used_vram_mb),
            free_mb=round(status.free_vram_mb),
            budget_mb=self.max_vram_mb,
            device=self.device_index,
        )

        if status.used_vram_mb > self.max_vram_mb:
            raise RuntimeError(
                f"GPU VRAM budget exceeded before operation: "
                f"{status.used_vram_mb:.0f} MB used > {self.max_vram_mb:.0f} MB budget. "
                f"Free some GPU memory before proceeding."
            )

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        status = get_gpu_status(self.device_index)
        delta = status.used_vram_mb - (self._entry_status.used_vram_mb if self._entry_status else 0)

        logger.info(
            "GPUGuard: exiting",
            used_mb=round(status.used_vram_mb),
            free_mb=round(status.free_vram_mb),
            delta_mb=round(delta),
            device=self.device_index,
        )

        if status.used_vram_mb > self.max_vram_mb:
            logger.warning(
                "GPUGuard: VRAM budget exceeded during operation",
                used_mb=round(status.used_vram_mb),
                budget_mb=self.max_vram_mb,
            )

    # Support async with-statement as well (delegates to sync)
    async def __aenter__(self) -> "GPUGuard":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        self.__exit__(exc_type, exc_val, exc_tb)

    @property
    def entry_status(self) -> Optional[GPUStatus]:
        """GPU status captured on context entry (None if not yet entered)."""
        return self._entry_status


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GPU resource guard and status checker for RTX 4060.",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=0,
        help="CUDA device index (default: 0).",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=7500,
        help="VRAM budget in MB for guard test (default: 7500).",
    )
    parser.add_argument(
        "--guard-test",
        action="store_true",
        help="Run a GPUGuard enter/exit cycle to verify budget enforcement.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    print("\n  GPU Status")
    print("  " + "=" * 60)

    try:
        status = log_gpu_snapshot(device_index=args.device)
        print(f"  {status}")
        print()
        print(f"  Device:       {status.name}")
        print(f"  VRAM Used:    {status.used_vram_mb:.0f} MB / {status.total_vram_mb:.0f} MB ({status.used_pct:.1f}%)")
        print(f"  VRAM Free:    {status.free_vram_mb:.0f} MB")
        print(f"  Temperature:  {status.temperature_c}°C")
        print(f"  GPU Util:     {status.utilization_pct:.0f}%")
        if status.power_draw_w:
            print(f"  Power Draw:   {status.power_draw_w:.1f} W")
    except RuntimeError as exc:
        print(f"  ERROR: {exc}")
        sys.exit(1)

    if args.guard_test:
        print()
        print(f"  Running GPUGuard test (budget={args.budget:.0f} MB)...")
        try:
            with GPUGuard(max_vram_mb=args.budget, device_index=args.device):
                print("  ✅  GPUGuard entered successfully.")
            print("  ✅  GPUGuard exited successfully.")
        except RuntimeError as exc:
            print(f"  ❌  GPUGuard rejected entry: {exc}")

    print("  " + "=" * 60 + "\n")
