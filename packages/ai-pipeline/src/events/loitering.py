"""Loitering detection inside polygon-based zones using Shapely geometry."""

import logging
from typing import List

import numpy as np
import shapely.geometry as sg

from events.base_detector import Event, EventDetector
from tracking.bytetrack import STrack

logger = logging.getLogger(__name__)


class LoiteringDetector(EventDetector):
    """Detects when tracked objects dwell inside polygon zones longer than a configured threshold."""

    def __init__(self, camera_id: str):
        """Initialize loitering detector with default rules."""
        super().__init__(camera_id)
        self.rules = {
            "dwell_threshold_ms": 30000,  # 30 seconds
            "severity": "MEDIUM",
            "zones": {}  # dict of zone_id -> list of coordinate points [(x1,y1), (x2,y2)...]
        }
        self._polygons: dict = {}

    def configure(self, rules: dict) -> None:
        """Configure rules and instantiate Shapely Polygon objects."""
        super().configure(rules)
        # Parse polygon zones
        self._polygons.clear()
        for zone_id, points in self.rules.get("zones", {}).items():
            if len(points) >= 3:
                try:
                    self._polygons[zone_id] = sg.Polygon(points)
                    logger.info("Configured loitering polygon zone '%s' with %d vertices.", zone_id, len(points))
                except Exception as e:
                    logger.error("Failed to build Shapely Polygon for zone '%s': %s", zone_id, e)

    def _get_track_center(self, track: STrack) -> np.ndarray:
        """Get track center (x, y)."""
        x1, y1, x2, y2 = track.bbox
        return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float32)

    def detect(self, tracks: List[STrack], frame: np.ndarray, timestamp_ms: int) -> List[Event]:
        """Detect loitering inside the configured zones."""
        if not self._polygons:
            return []

        dwell_thresh = self.rules.get("dwell_threshold_ms", 30000)
        events = []

        for track in tracks:
            center = self._get_track_center(track)
            point = sg.Point(center[0], center[1])
            
            # Retrieve/initialize loitering history inside track metadata
            track_meta = track.metadata
            loiter_history = track_meta.setdefault("loitering_zones", {})

            # Check track location against each polygon zone
            for zone_id, polygon in self._polygons.items():
                is_inside = point.within(polygon)

                if is_inside:
                    if zone_id not in loiter_history:
                        # Record entry timestamp
                        loiter_history[zone_id] = timestamp_ms

                    # Calculate dwell time
                    entry_time = loiter_history[zone_id]
                    dwell_duration = timestamp_ms - entry_time

                    if dwell_duration >= dwell_thresh:
                        event_type = "loitering"
                        
                        # Deduplicate
                        if self.should_suppress(event_type, zone_id, timestamp_ms):
                            continue

                        events.append(
                            Event(
                                camera_id=self.camera_id,
                                event_type=event_type,
                                severity=self.rules.get("severity", "MEDIUM"),
                                timestamp_ms=timestamp_ms,
                                zone_id=zone_id,
                                metadata={
                                    "track_id": track.track_id,
                                    "dwell_time_seconds": dwell_duration / 1000.0,
                                    "class_label": track.class_label,
                                    "bounding_box": track.bbox.tolist(),
                                },
                            )
                        )
                else:
                    # Remove zone record if track leaves the zone
                    if zone_id in loiter_history:
                        del loiter_history[zone_id]

        return events
