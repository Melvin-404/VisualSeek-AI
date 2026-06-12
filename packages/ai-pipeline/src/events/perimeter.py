"""Perimeter breach (line crossing / zone entry) and wrong direction flow detection."""

import logging
from typing import List, Tuple

import numpy as np
import shapely.geometry as sg

from events.base_detector import Event, EventDetector
from tracking.bytetrack import STrack

logger = logging.getLogger(__name__)


class PerimeterBreachDetector(EventDetector):
    """Detects virtual line crossing (tripwire) or entry breaches into security zones."""

    def __init__(self, camera_id: str):
        """Initialize perimeter breach detector."""
        super().__init__(camera_id)
        self.rules = {
            "severity": "CRITICAL",
            "lines": {},  # line_id -> [(x1, y1), (x2, y2)] (tripwires)
            "zones": {}   # zone_id -> [(x1, y1), (x2, y2), ...] (breach zones)
        }
        self._tripwires: dict = {}
        self._zones: dict = {}

    def configure(self, rules: dict) -> None:
        """Instantiate Shapely tripwires and polygons from configuration."""
        super().configure(rules)
        self._tripwires.clear()
        self._zones.clear()

        # Parse tripwire lines
        for line_id, points in self.rules.get("lines", {}).items():
            if len(points) == 2:
                try:
                    self._tripwires[line_id] = sg.LineString(points)
                    logger.info("Configured tripwire line '%s'.", line_id)
                except Exception as e:
                    logger.error("Failed to build tripwire line '%s': %s", line_id, e)

        # Parse breach zones
        for zone_id, points in self.rules.get("zones", {}).items():
            if len(points) >= 3:
                try:
                    self._zones[zone_id] = sg.Polygon(points)
                    logger.info("Configured breach zone polygon '%s'.", zone_id)
                except Exception as e:
                    logger.error("Failed to build breach zone '%s': %s", zone_id, e)

    def _get_track_center(self, bbox: np.ndarray) -> np.ndarray:
        """Get bounding box center (x, y)."""
        x1, y1, x2, y2 = bbox
        return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float32)

    def detect(self, tracks: List[STrack], frame: np.ndarray, timestamp_ms: int) -> List[Event]:
        """Detect tripwire crossings and zone entries."""
        events = []

        for track in tracks:
            if len(track.history) < 2:
                continue

            # Get current and previous coordinates
            curr_center = self._get_track_center(track.bbox)
            prev_center = self._get_track_center(track.history[-2][1])

            curr_point = sg.Point(curr_center[0], curr_center[1])
            prev_point = sg.Point(prev_center[0], prev_center[1])

            # Track segment line representing movement between frames
            track_segment = sg.LineString([prev_center, curr_center])

            # 1. Evaluate tripwire line crossings
            for line_id, tripwire in self._tripwires.items():
                if track_segment.intersects(tripwire):
                    event_type = "perimeter_breach"
                    zone_id = line_id
                    
                    if self.should_suppress(event_type, zone_id, timestamp_ms):
                        continue

                    events.append(
                        Event(
                            camera_id=self.camera_id,
                            event_type=event_type,
                            severity=self.rules.get("severity", "CRITICAL"),
                            timestamp_ms=timestamp_ms,
                            zone_id=zone_id,
                            metadata={
                                "breach_type": "tripwire_crossing",
                                "track_id": track.track_id,
                                "class_label": track.class_label,
                                "crossing_segment": [[float(prev_center[0]), float(prev_center[1])],
                                                     [float(curr_center[0]), float(curr_center[1])]],
                            },
                        )
                    )

            # 2. Evaluate zone entries (breached boundary)
            for zone_id, zone_poly in self._zones.items():
                # Crosses boundary if previously OUTSIDE and now INSIDE
                was_outside = not prev_point.within(zone_poly)
                is_inside = curr_point.within(zone_poly)

                if was_outside and is_inside:
                    event_type = "perimeter_breach"
                    
                    if self.should_suppress(event_type, zone_id, timestamp_ms):
                        continue

                    events.append(
                        Event(
                            camera_id=self.camera_id,
                            event_type=event_type,
                            severity=self.rules.get("severity", "CRITICAL"),
                            timestamp_ms=timestamp_ms,
                            zone_id=zone_id,
                            metadata={
                                "breach_type": "zone_entry",
                                "track_id": track.track_id,
                                "class_label": track.class_label,
                                "bounding_box": track.bbox.tolist(),
                            },
                        )
                    )

        return events


class WrongDirectionDetector(EventDetector):
    """Detects objects moving against the allowed flow vector."""

    def __init__(self, camera_id: str):
        """Initialize wrong direction detector."""
        super().__init__(camera_id)
        self.rules = {
            "severity": "MEDIUM",
            "allowed_direction": [1.0, 0.0],  # Vector pointing right
            "angle_threshold": 90.0,          # Angle limit in degrees
            "history_frames": 5,              # Steps back to estimate vector
            "zone_id": None
        }

    def _get_track_center(self, bbox: np.ndarray) -> np.ndarray:
        """Get bounding box center (x, y)."""
        x1, y1, x2, y2 = bbox
        return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float32)

    def detect(self, tracks: List[STrack], frame: np.ndarray, timestamp_ms: int) -> List[Event]:
        """Detect tracks moving against allowed flow direction."""
        history_len = self.rules.get("history_frames", 5)
        allowed_vec = np.array(self.rules.get("allowed_direction", [1.0, 0.0]), dtype=np.float32)
        
        # Normalize allowed vector
        allowed_norm = np.linalg.norm(allowed_vec)
        if allowed_norm > 0:
            allowed_vec /= allowed_norm
        else:
            return []

        angle_limit = self.rules.get("angle_threshold", 90.0)
        # Cosine of threshold angle (dot product threshold)
        # wrong direction if dot product < cos(threshold_radians)
        # e.g., 90 deg -> cos(90) = 0. So dot < 0 means wrong direction (opposing vector)
        cos_thresh = np.cos(np.radians(180.0 - angle_limit))

        events = []

        for track in tracks:
            # Need sufficient history to determine stable motion vector
            if len(track.history) < history_len:
                continue

            curr_center = self._get_track_center(track.bbox)
            prev_center = self._get_track_center(track.history[-history_len][1])

            # Calculate direction vector
            motion_vec = curr_center - prev_center
            motion_norm = np.linalg.norm(motion_vec)

            # Skip small stationary jitter
            if motion_norm < 10.0:
                continue

            motion_vec /= motion_norm

            # Calculate dot product
            dot_product = float(np.dot(motion_vec, allowed_vec))

            # If moving opposing direction
            # If dot product is negative and exceeds threshold angle deviation
            if dot_product < cos_thresh:
                event_type = "wrong_direction"
                zone_id = self.rules.get("zone_id")

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
                            "class_label": track.class_label,
                            "dot_product": dot_product,
                            "motion_vector": [float(motion_vec[0]), float(motion_vec[1])],
                        },
                    )
                )

        return events
