"""RTSP stream ingestion worker with GPU-accelerated decoding.

Captures frames from RTSP cameras using OpenCV with optional NVIDIA
hardware decode (nvdec). Provides automatic reconnection with
exponential backoff and thread-safe camera registry.
"""

import logging
import signal
import subprocess
import json
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from ingestion.config import IngestionConfig
from ingestion.segmenter import VideoSegmenter
from ingestion.quality_check import FrameQualityChecker
from ingestion.health_monitor import StreamHealthMonitor

logger = logging.getLogger(__name__)


@dataclass
class StreamInfo:
    """Metadata about an RTSP stream obtained via ffprobe."""

    codec: str = "unknown"
    width: int = 0
    height: int = 0
    fps: float = 0.0
    transport: str = "tcp"


# Thread-safe global camera registry
_camera_registry: dict[str, "RTSPIngestionWorker"] = {}
_registry_lock = threading.Lock()


def get_active_workers() -> dict[str, "RTSPIngestionWorker"]:
    """Return a snapshot of the active camera workers."""
    with _registry_lock:
        return dict(_camera_registry)


class RTSPIngestionWorker:
    """Worker that captures frames from an RTSP stream.

    Supports NVIDIA hardware decoding when available, automatic
    reconnection with exponential backoff, and graceful shutdown.

    Args:
        camera_id: Unique identifier for the camera.
        rtsp_url: Full RTSP URL including credentials if needed.
        org_id: Organization ID for metadata tagging.
        config: Ingestion configuration instance.
    """

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        org_id: str,
        config: Optional[IngestionConfig] = None,
    ) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.org_id = org_id
        self.config = config or IngestionConfig()

        self._cap: Optional[cv2.VideoCapture] = None
        self._running = False
        self._shutdown_event = threading.Event()
        self._reconnect_attempt = 0
        self._stream_info: Optional[StreamInfo] = None

        # Collaborators
        self._segmenter = VideoSegmenter(camera_id, self.config)
        self._quality_checker = FrameQualityChecker(self.config)
        self._health_monitor = StreamHealthMonitor()

        # Register in global registry
        with _registry_lock:
            _camera_registry[camera_id] = self

    def get_stream_info(self) -> StreamInfo:
        """Probe the RTSP stream using ffprobe to detect capabilities.

        Returns:
            StreamInfo with codec, resolution, fps, and transport details.
        """
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-rtsp_transport", self.config.rtsp.transport,
                self.rtsp_url,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                logger.warning(
                    "ffprobe failed for camera %s: %s",
                    self.camera_id, result.stderr[:200]
                )
                return StreamInfo()

            probe_data = json.loads(result.stdout)
            for stream in probe_data.get("streams", []):
                if stream.get("codec_type") == "video":
                    fps_parts = stream.get("r_frame_rate", "30/1").split("/")
                    fps = (
                        float(fps_parts[0]) / float(fps_parts[1])
                        if len(fps_parts) == 2 and float(fps_parts[1]) > 0
                        else 30.0
                    )
                    info = StreamInfo(
                        codec=stream.get("codec_name", "unknown"),
                        width=int(stream.get("width", 0)),
                        height=int(stream.get("height", 0)),
                        fps=fps,
                    )
                    self._stream_info = info
                    logger.info(
                        "Stream info for %s: %s %dx%d @ %.1ffps",
                        self.camera_id, info.codec, info.width, info.height, info.fps
                    )
                    return info
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
            logger.error("ffprobe error for camera %s: %s", self.camera_id, exc)

        return StreamInfo()

    def connect(self) -> bool:
        """Open the RTSP stream with OpenCV VideoCapture.

        Attempts GPU-accelerated decode first, falls back to CPU.

        Returns:
            True if connection succeeded, False otherwise.
        """
        # Release any existing capture
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        try:
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(self.config.rtsp.frame_timeout_s * 1000))

            # Try enabling hardware acceleration if configured
            if self.config.gpu.enable_nvdec:
                cap.set(cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY)
                cap.set(cv2.CAP_PROP_HW_DEVICE, self.config.gpu.device_id)
                logger.info("Attempting GPU decode for camera %s", self.camera_id)

            if not cap.isOpened():
                logger.error("Failed to open RTSP stream for camera %s", self.camera_id)
                self._health_monitor.record_error(
                    self.camera_id, "Connection failed"
                )
                return False

            self._cap = cap
            self._reconnect_attempt = 0
            self._health_monitor.record_frame(self.camera_id)  # Reset health

            # Get stream properties
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

            logger.info(
                "Connected to camera %s: %dx%d @ %.1ffps",
                self.camera_id, width, height, fps
            )
            return True

        except cv2.error as exc:
            logger.error("OpenCV error connecting camera %s: %s", self.camera_id, exc)
            self._health_monitor.record_error(self.camera_id, str(exc))
            return False

    def read_frame(self) -> tuple[Optional[np.ndarray], dict]:
        """Read a single frame from the stream.

        Returns:
            Tuple of (frame_or_None, metadata_dict).
        """
        if self._cap is None or not self._cap.isOpened():
            return None, {"error": "Stream not connected"}

        ret, frame = self._cap.read()
        if not ret or frame is None:
            self._health_monitor.record_error(
                self.camera_id, "Frame read failed"
            )
            return None, {"error": "Frame read failed"}

        self._health_monitor.record_frame(self.camera_id)
        metadata = {
            "camera_id": self.camera_id,
            "timestamp": time.time(),
            "width": frame.shape[1],
            "height": frame.shape[0],
            "channels": frame.shape[2] if len(frame.shape) > 2 else 1,
        }
        return frame, metadata

    def reconnect(self) -> bool:
        """Reconnect with exponential backoff.

        Returns:
            True if reconnection succeeded.
        """
        delay = min(
            self.config.rtsp.reconnect_base_delay_s * (2 ** self._reconnect_attempt),
            self.config.rtsp.reconnect_max_delay_s,
        )
        self._reconnect_attempt += 1

        logger.warning(
            "Reconnecting camera %s (attempt %d, delay %.1fs)",
            self.camera_id, self._reconnect_attempt, delay
        )
        self._shutdown_event.wait(timeout=delay)

        if self._shutdown_event.is_set():
            return False

        return self.connect()

    def run(self) -> None:
        """Main capture loop: reads frames, segments, and stores.

        Runs until shutdown() is called or SIGTERM/SIGINT received.
        """
        self._running = True
        self._shutdown_event.clear()

        # Register signal handlers for graceful shutdown
        def handle_signal(*args):
            self.shutdown()

        original_sigterm = signal.getsignal(signal.SIGTERM)
        original_sigint = signal.getsignal(signal.SIGINT)
        
        try:
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGINT, handle_signal)
        except ValueError:
            # Signal only works in main thread of main interpreter
            pass

        try:
            # Probe stream first
            self.get_stream_info()

            # Initial connection
            if not self.connect():
                logger.error("Initial connection failed for camera %s", self.camera_id)
                while not self._shutdown_event.is_set():
                    if self.reconnect():
                        break
                else:
                    return

            frame_count = 0
            consecutive_failures = 0
            max_consecutive_failures = 30  # ~1 second at 30fps

            logger.info("Starting capture loop for camera %s", self.camera_id)

            while not self._shutdown_event.is_set():
                frame, metadata = self.read_frame()

                if frame is None:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        logger.warning(
                            "Camera %s: %d consecutive failures, reconnecting",
                            self.camera_id, consecutive_failures
                        )
                        if not self.reconnect():
                            continue
                        consecutive_failures = 0
                    continue

                consecutive_failures = 0
                frame_count += 1

                # Quality check at configured interval
                if frame_count % self.config.quality.check_interval_frames == 0:
                    report = self._quality_checker.check(frame, None)
                    if not report.is_acceptable:
                        logger.debug(
                            "Camera %s: frame %d quality issue (blur=%.1f, brightness=%.1f)",
                            self.camera_id, frame_count,
                            report.blur_score, report.brightness_score
                        )

                # Add frame to segmenter
                segment_result = self._segmenter.add_frame(
                    frame, metadata["timestamp"]
                )

                if segment_result is not None:
                    # A complete segment is ready — dispatch for upload
                    logger.info(
                        "Camera %s: segment ready (%.1fs, %d frames, %s)",
                        self.camera_id,
                        segment_result.duration_ms / 1000,
                        segment_result.frame_count,
                        segment_result.file_path,
                    )
                    # Import here to avoid circular dependency
                    from ingestion.tasks import process_segment
                    process_segment.delay(
                        segment_path=segment_result.file_path,
                        camera_id=self.camera_id,
                        org_id=self.org_id,
                        metadata=segment_result.to_dict(),
                    )

        finally:
            # Flush any remaining frames
            flushed = self._segmenter.flush()
            if flushed is not None:
                from ingestion.tasks import process_segment
                process_segment.delay(
                    segment_path=flushed.file_path,
                    camera_id=self.camera_id,
                    org_id=self.org_id,
                    metadata=flushed.to_dict(),
                )

            # Release resources
            if self._cap is not None:
                self._cap.release()
                self._cap = None

            # Unregister
            with _registry_lock:
                _camera_registry.pop(self.camera_id, None)

            try:
                # Restore signal handlers
                signal.signal(signal.SIGTERM, original_sigterm)
                signal.signal(signal.SIGINT, original_sigint)
            except ValueError:
                pass

            self._running = False
            logger.info("Camera %s: capture loop stopped", self.camera_id)

    def shutdown(self) -> None:
        """Signal the worker to stop gracefully."""
        logger.info("Shutdown requested for camera %s", self.camera_id)
        self._shutdown_event.set()

    @property
    def is_running(self) -> bool:
        """Whether the capture loop is active."""
        return self._running
