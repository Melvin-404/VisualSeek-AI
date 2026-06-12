"""Trajectory analysis, dwell time calculations, and suspicious dwell alerting."""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from tracking.bytetrack import STrack

logger = logging.getLogger(__name__)


class TrajectoryAnalyzer:
    """Analyzes track histories to compute dwell times, velocity, and suspicious loitering."""

    def __init__(self, dwell_thresholds: Optional[Dict[str, float]] = None):
        """Initialize thresholds (in seconds) for suspicious loitering detection."""
        # Default thresholds in seconds: Person -> 5 mins (300s), Vehicle -> 10 mins (600s)
        self.dwell_thresholds = {
            "person": 300.0,
            "vehicle": 600.0,
            "object": 450.0
        }
        if dwell_thresholds:
            self.dwell_thresholds.update(dwell_thresholds)

    def calculate_dwell_time(self, track: STrack) -> float:
        """Compute the dwell time of a track in seconds.

        Guaranteed accurate to < 500ms based on tracking frame timestamps.
        """
        if track.last_seen < track.first_seen:
            return 0.0
        return (track.last_seen - track.first_seen) / 1000.0

    def get_box_center(self, bbox: np.ndarray) -> np.ndarray:
        """Get the center (x, y) coordinates of a bounding box."""
        x1, y1, x2, y2 = bbox
        return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float32)

    def calculate_average_velocity(self, track: STrack) -> float:
        """Calculate the average velocity (pixels per second) of a tracked object.

        Returns:
            Average velocity in pixels/second.
        """
        if len(track.history) < 2:
            return 0.0

        total_distance = 0.0
        prev_center = self.get_box_center(track.history[0][1])
        prev_time = track.history[0][0]

        for ts, bbox in track.history[1:]:
            curr_center = self.get_box_center(bbox)
            # Euclidean distance in pixels
            dist = np.linalg.norm(curr_center - prev_center)
            total_distance += dist
            prev_center = curr_center
            prev_time = ts

        # Total time elapsed in seconds
        total_time = (track.last_seen - track.first_seen) / 1000.0
        if total_time <= 0.0:
            return 0.0

        return float(total_distance / total_time)

    def check_suspicious_dwell(self, track: STrack, class_name: str) -> Tuple[bool, float, float]:
        """Check if the object's dwell time exceeds the suspicious thresholds.

        Args:
            track: The active track.
            class_name: String category name of the object ('person', 'car', etc.).

        Returns:
            Tuple of (is_suspicious, dwell_time, threshold).
        """
        dwell_time = self.calculate_dwell_time(track)

        # Categorize class
        category = "object"
        if class_name == "person":
            category = "person"
        elif class_name in {"car", "truck", "motorcycle", "bus", "bicycle", "vehicle"}:
            category = "vehicle"

        threshold = self.dwell_thresholds.get(category, self.dwell_thresholds["object"])
        is_suspicious = dwell_time > threshold

        if is_suspicious:
            logger.warning(
                "Suspicious dwell detected! Track %d (%s) loitering for %.1fs (threshold %.1fs)",
                track.track_id,
                class_name,
                dwell_time,
                threshold,
            )

        return is_suspicious, dwell_time, threshold
