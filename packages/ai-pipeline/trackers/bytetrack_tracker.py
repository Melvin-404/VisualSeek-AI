"""ByteTrack multi-object tracker wrapper and configuration.

This module provides the ByteTrackWrapper class, which integrates the local
ByteTracker implementation to manage track IDs for detections across video frames.
"""

from dataclasses import dataclass
import logging
from typing import List, Optional, Tuple
import numpy as np

# Ensure packages/ai-pipeline/src is in import path if needed, but since it is inside packages/ai-pipeline,
# it can import directly from tracking.bytetrack.
from tracking.bytetrack import ByteTracker, STrack

logger = logging.getLogger(__name__)

@dataclass
class TrackerConfig:
    """Configuration settings for ByteTrackWrapper."""
    track_thresh: float = 0.45
    track_buffer: int = 60  # Updated to 60 as per Step 3.5 to mitigate ID switching
    match_thresh: float = 0.8
    min_box_area: float = 400.0
    frame_rate: int = 30
    high_thresh: float = 0.45
    low_thresh: float = 0.20

def _compute_iou_single(box1: Tuple[float, float, float, float], box2: Tuple[float, float, float, float]) -> float:
    """Compute IoU between two single bounding boxes [x1, y1, x2, y2]."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    return intersection / max(union, 1e-6)

class ByteTrackWrapper:
    """Wrapper class around ByteTracker to assign persistent track IDs to Detection objects."""

    def __init__(self, config: TrackerConfig):
        """Initialize the ByteTrackWrapper.

        Args:
            config: TrackerConfig configuration settings.
        """
        self.config = config
        # Convert track_buffer (frames) to max_time_lost_ms using frame_rate
        max_time_lost_ms = int((config.track_buffer / config.frame_rate) * 1000.0)

        # Initialize local ByteTracker
        self.tracker = ByteTracker(
            track_thresh=config.track_thresh,
            high_thresh=config.high_thresh,
            match_thresh=config.match_thresh,
            max_time_lost_ms=max_time_lost_ms,
            min_hits=2  # default confirm hits
        )
        logger.info(
            "ByteTrackWrapper initialized — track_thresh=%s, match_thresh=%s, buffer_frames=%d (%dms)",
            config.track_thresh,
            config.match_thresh,
            config.track_buffer,
            max_time_lost_ms
        )

    def update(self, detections: List[any], frame_id: int, frame: Optional[np.ndarray] = None) -> List[any]:
        """Update tracks and assign track IDs to Detection objects in-place.

        Args:
            detections: List of Detection objects (from detector).
            frame_id: Monotonically increasing frame counter.
            frame: Optional raw frame image (required for ReID features).

        Returns:
            The list of updated Detection objects with populated track_id fields.
        """
        if not detections:
            # Feed empty detections array to update tracker internal state
            self.tracker.update(np.empty((0, 6)), np.zeros((1, 1, 3), dtype=np.uint8), int((frame_id / self.config.frame_rate) * 1000.0))
            return []

        # Convert Detection objects to detections numpy array of shape (N, 6)
        # BBox format: [x1, y1, x2, y2, score, class_id]
        dets_list = []
        for det in detections:
            x1, y1, x2, y2 = det.bbox_xyxy
            dets_list.append([x1, y1, x2, y2, det.confidence, det.class_id])
        dets_array = np.array(dets_list, dtype=np.float32)

        # Compute timestamp
        timestamp_ms = int(detections[0].timestamp_ms)

        # Use mock frame if not provided
        if frame is None:
            frame = np.zeros((640, 640, 3), dtype=np.uint8)

        # Run tracker update
        stracks = self.tracker.update(dets_array, frame, timestamp_ms)

        # Reset all track_ids to None first
        for det in detections:
            det.track_id = None

        # Associate track_ids back to Detection objects in-place
        for strack in stracks:
            best_det = None
            best_iou = 0.0
            for det in detections:
                iou = _compute_iou_single(strack.bbox, det.bbox_xyxy)
                if iou > best_iou:
                    best_iou = iou
                    best_det = det
            if best_det is not None and best_iou >= 0.7:
                best_det.track_id = int(strack.track_id)

        return detections

    def reset(self) -> None:
        """Reset the tracker's internal track pools and frame counter."""
        self.tracker.tracked_tracks.clear()
        self.tracker.lost_tracks.clear()
        self.tracker.frame_id = 0
        self.tracker.next_track_id = 1
        logger.info("Tracker state reset completed.")
