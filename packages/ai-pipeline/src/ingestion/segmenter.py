"""Video segmentation with adaptive chunking and frame overlap.

Splits continuous RTSP capture into fixed-duration segments with
configurable overlap for seamless analysis across segment boundaries.
"""

import logging
import os
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ingestion.config import IngestionConfig

logger = logging.getLogger(__name__)


@dataclass
class SegmentResult:
    """Metadata for a completed video segment."""

    file_path: str
    segment_id: str
    camera_id: str
    start_time: float  # Unix timestamp
    end_time: float  # Unix timestamp
    duration_ms: int
    fps: float
    resolution: str  # "WIDTHxHEIGHT"
    codec: str
    frame_count: int
    file_size_bytes: int

    def to_dict(self) -> dict:
        """Serialize to dictionary for Celery task payload."""
        return asdict(self)


class VideoSegmenter:
    """Segments a continuous frame stream into fixed-duration video files.

    Frames are buffered and written to MP4 segments when the configured
    duration is reached. The last `overlap_s` seconds of frames are
    retained for the next segment to ensure continuity.

    Args:
        camera_id: Camera identifier for file naming.
        config: Ingestion configuration.
    """

    def __init__(self, camera_id: str, config: Optional[IngestionConfig] = None) -> None:
        self.camera_id = camera_id
        self.config = config or IngestionConfig()

        self._frame_buffer: list[tuple[np.ndarray, float]] = []  # (frame, timestamp)
        self._segment_start_time: Optional[float] = None
        self._writer: Optional[cv2.VideoWriter] = None
        self._fps: float = 30.0
        self._frame_size: Optional[tuple[int, int]] = None  # (width, height)

        # Ensure temp directory exists
        os.makedirs(self.config.segment.temp_dir, exist_ok=True)

    def add_frame(
        self, frame: np.ndarray, timestamp: float
    ) -> Optional[SegmentResult]:
        """Add a frame to the current segment buffer.

        When the buffer duration reaches segment_duration_s, the segment
        is finalized and a SegmentResult is returned.

        Args:
            frame: BGR image array from OpenCV.
            timestamp: Unix timestamp of the frame.

        Returns:
            SegmentResult if a segment was completed, None otherwise.
        """
        # Initialize segment start time
        if self._segment_start_time is None:
            self._segment_start_time = timestamp

        # Detect frame size on first frame
        if self._frame_size is None:
            h, w = frame.shape[:2]
            self._frame_size = (w, h)

        self._frame_buffer.append((frame, timestamp))

        # Check if segment duration reached
        elapsed = timestamp - self._segment_start_time
        if elapsed >= self.config.segment.duration_s:
            return self._finalize_segment()

        return None

    def _finalize_segment(self) -> Optional[SegmentResult]:
        """Write buffered frames to disk as an MP4 segment.

        Returns:
            SegmentResult with file metadata, or None on failure."""
        if not self._frame_buffer or self._frame_size is None:
            return None

        segment_id = str(uuid.uuid4())
        filename = f"{self.camera_id}_{segment_id}{self.config.segment.output_extension}"
        file_path = os.path.join(self.config.segment.temp_dir, filename)

        start_time = self._frame_buffer[0][1]
        end_time = self._frame_buffer[-1][1]
        frame_count = len(self._frame_buffer)
        duration_s = end_time - start_time

        # Calculate actual FPS from timestamps
        if duration_s > 0 and frame_count > 1:
            self._fps = (frame_count - 1) / duration_s
        fps = max(1.0, self._fps)

        # Write frames using OpenCV VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*self.config.segment.output_codec)
        writer = cv2.VideoWriter(file_path, fourcc, fps, self._frame_size)

        if not writer.isOpened():
            logger.error(
                "Failed to open VideoWriter for segment %s (codec=%s, size=%s)",
                segment_id, self.config.segment.output_codec, self._frame_size
            )
            return None

        try:
            for frame_data, _ in self._frame_buffer:
                writer.write(frame_data)
        finally:
            writer.release()

        # Get file size
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

        result = SegmentResult(
            file_path=file_path,
            segment_id=segment_id,
            camera_id=self.camera_id,
            start_time=start_time,
            end_time=end_time,
            duration_ms=int(duration_s * 1000),
            fps=round(fps, 2),
            resolution=f"{self._frame_size[0]}x{self._frame_size[1]}",
            codec=self.config.segment.output_codec,
            frame_count=frame_count,
            file_size_bytes=file_size,
        )

        logger.info(
            "Segment finalized: %s (%.1fs, %d frames, %.1f KB)",
            segment_id, duration_s, frame_count, file_size / 1024
        )

        # Retain overlap frames for next segment
        overlap_frames = self._get_overlap_frames()
        self._frame_buffer = overlap_frames
        if overlap_frames:
            self._segment_start_time = overlap_frames[0][1]
        else:
            self._segment_start_time = None

        return result

    def _get_overlap_frames(self) -> list[tuple[np.ndarray, float]]:
        """Extract the last `overlap_s` seconds of frames for continuity."""
        if not self._frame_buffer:
            return []

        overlap_s = self.config.segment.overlap_s
        cutoff_time = self._frame_buffer[-1][1] - overlap_s

        overlap = [
            (frame, ts)
            for frame, ts in self._frame_buffer
            if ts >= cutoff_time
        ]
        return overlap

    def flush(self) -> Optional[SegmentResult]:
        """Flush remaining frames as a partial segment.

        Called during shutdown to avoid losing buffered frames.

        Returns:
            SegmentResult if frames were flushed, None otherwise.
        """
        if len(self._frame_buffer) < 2:
            self._frame_buffer.clear()
            return None

        logger.info(
            "Flushing %d remaining frames for camera %s",
            len(self._frame_buffer), self.camera_id
        )
        return self._finalize_segment()

    def reset(self) -> None:
        """Reset the segmenter, discarding all buffered frames."""
        self._frame_buffer.clear()
        self._segment_start_time = None
        self._frame_size = None
