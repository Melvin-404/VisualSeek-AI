"""Stream health monitoring for RTSP ingestion workers.

Tracks per-camera health metrics including FPS, frame drops,
reconnection count, and error rates. Thread-safe for concurrent
multi-camera ingestion.
"""

import logging
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Camera stream health classification."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    OFFLINE = "offline"


@dataclass
class StreamHealth:
    """Health metrics for a single camera stream."""

    camera_id: str
    status: HealthStatus = HealthStatus.OFFLINE
    current_fps: float = 0.0
    target_fps: float = 30.0
    frame_count: int = 0
    frame_drops: int = 0
    reconnect_count: int = 0
    error_count: int = 0
    last_frame_time: float = 0.0
    last_error: Optional[str] = None
    uptime_s: float = 0.0
    started_at: float = field(default_factory=time.time)


class StreamHealthMonitor:
    """Monitors health of all active RTSP streams.

    Thread-safe: uses per-camera locks to avoid contention
    when multiple ingestion workers report concurrently.
    """

    # Thresholds for health classification
    FPS_DEGRADED_RATIO = 0.7  # Below 70% of target FPS = degraded
    FPS_CRITICAL_RATIO = 0.3  # Below 30% of target FPS = critical
    ERROR_DEGRADED_THRESHOLD = 5  # Errors in window = degraded
    ERROR_CRITICAL_THRESHOLD = 20  # Errors in window = critical
    STALE_TIMEOUT_S = 30.0  # No frames for 30s = offline

    def __init__(self) -> None:
        self._streams: dict[str, StreamHealth] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._fps_windows: dict[str, list[float]] = {}  # Rolling timestamps

    def _ensure_stream(self, camera_id: str) -> None:
        """Ensure a health entry and lock exist for the camera."""
        if camera_id not in self._streams:
            with self._global_lock:
                if camera_id not in self._streams:
                    self._streams[camera_id] = StreamHealth(camera_id=camera_id)
                    self._locks[camera_id] = threading.Lock()
                    self._fps_windows[camera_id] = []

    def record_frame(self, camera_id: str) -> None:
        """Record a successfully captured frame.

        Updates FPS calculation and resets stale timer.

        Args:
            camera_id: Camera identifier.
        """
        self._ensure_stream(camera_id)
        lock = self._locks[camera_id]

        with lock:
            health = self._streams[camera_id]
            now = time.time()
            health.frame_count += 1
            health.last_frame_time = now
            health.uptime_s = now - health.started_at

            # Rolling FPS window (last 2 seconds of timestamps)
            window = self._fps_windows[camera_id]
            window.append(now)
            cutoff = now - 2.0
            self._fps_windows[camera_id] = [
                t for t in window if t > cutoff
            ]
            window_len = len(self._fps_windows[camera_id])
            health.current_fps = window_len / 2.0 if window_len > 1 else 0.0

            # Update status
            health.status = self._classify(health)

    def record_error(self, camera_id: str, error: str) -> None:
        """Record a stream error.

        Args:
            camera_id: Camera identifier.
            error: Error description string.
        """
        self._ensure_stream(camera_id)
        lock = self._locks[camera_id]

        with lock:
            health = self._streams[camera_id]
            health.error_count += 1
            health.last_error = error
            health.status = self._classify(health)

        logger.warning(
            "Camera %s error #%d: %s",
            camera_id, health.error_count, error
        )

    def record_reconnect(self, camera_id: str) -> None:
        """Record a reconnection attempt."""
        self._ensure_stream(camera_id)
        with self._locks[camera_id]:
            self._streams[camera_id].reconnect_count += 1

    def get_health(self, camera_id: str) -> StreamHealth:
        """Get current health for a specific camera.

        Args:
            camera_id: Camera identifier.

        Returns:
            StreamHealth with current metrics and status.
        """
        self._ensure_stream(camera_id)
        with self._locks[camera_id]:
            health = self._streams[camera_id]
            # Check for stale stream
            if (
                health.last_frame_time > 0
                and time.time() - health.last_frame_time > self.STALE_TIMEOUT_S
            ):
                health.status = HealthStatus.OFFLINE
            return health

    def get_all_health(self) -> dict[str, StreamHealth]:
        """Get health summary for all tracked streams.

        Returns:
            Dictionary mapping camera_id to StreamHealth.
        """
        result = {}
        with self._global_lock:
            for camera_id in list(self._streams.keys()):
                result[camera_id] = self.get_health(camera_id)
        return result

    def remove_stream(self, camera_id: str) -> None:
        """Remove a camera from monitoring."""
        with self._global_lock:
            self._streams.pop(camera_id, None)
            self._locks.pop(camera_id, None)
            self._fps_windows.pop(camera_id, None)

    def _classify(self, health: StreamHealth) -> HealthStatus:
        """Classify stream health based on metrics."""
        # Check if stale
        if (
            health.last_frame_time > 0
            and time.time() - health.last_frame_time > self.STALE_TIMEOUT_S
        ):
            return HealthStatus.OFFLINE

        # Check error count
        if health.error_count >= self.ERROR_CRITICAL_THRESHOLD:
            return HealthStatus.CRITICAL
        if health.error_count >= self.ERROR_DEGRADED_THRESHOLD:
            return HealthStatus.DEGRADED

        # Check FPS
        if health.target_fps > 0 and health.current_fps > 0:
            fps_ratio = health.current_fps / health.target_fps
            if fps_ratio < self.FPS_CRITICAL_RATIO:
                return HealthStatus.CRITICAL
            if fps_ratio < self.FPS_DEGRADED_RATIO:
                return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY
