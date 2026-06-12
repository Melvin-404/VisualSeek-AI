"""Abandoned object detection based on track association and proximity thresholds."""

import logging
from typing import List, Optional, Tuple

import numpy as np

from events.base_detector import Event, EventDetector
from tracking.bytetrack import STrack

logger = logging.getLogger(__name__)

# Bounding box indices for bags/luggage in custom taxonomy:
# 26: backpack, 30: handbag, 32: suitcase
BAG_CLASSES = {26, 30, 32}


class AbandonedObjectDetector(EventDetector):
    """Detects when an object (backpack/suitcase/handbag) is abandoned by its owner."""

    def __init__(self, camera_id: str):
        """Initialize detector with default parameters."""
        super().__init__(camera_id)
        self.rules = {
            "abandoned_time_threshold_ms": 30000,  # 30 seconds
            "proximity_threshold": 120.0,          # Pixel distance to associate owner/bystanders
            "stationary_std_threshold": 4.0,       # Max coordinate std to count as stationary
            "severity": "CRITICAL",
            "zone_id": None
        }

    def _get_track_center(self, track: STrack) -> np.ndarray:
        """Get track center (x, y)."""
        x1, y1, x2, y2 = track.bbox
        return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float32)

    def _is_stationary(self, track: STrack, num_frames: int = 10) -> bool:
        """Evaluate if the track is stationary based on recent history variance."""
        if len(track.history) < 3:
            return False

        # Take the last N boxes in history
        recent = track.history[-num_frames:]
        centers = [self._get_track_center(STrack(box, 0.0, 0, ts)) for ts, box in recent]
        centers = np.array(centers)

        # Standard deviation of centers
        std_dev = np.std(centers, axis=0)
        max_std = self.rules.get("stationary_std_threshold", 4.0)
        
        # If both x and y deviations are below threshold, it's stationary
        return bool(np.all(std_dev < max_std))

    def detect(self, tracks: List[STrack], frame: np.ndarray, timestamp_ms: int) -> List[Event]:
        """Detect abandoned objects in the scene.

        Acceptance Criteria: Abandoned object alert within 30s of abandonment.
        """
        # Find all active bags and people
        bags = [t for t in tracks if t.class_label in BAG_CLASSES]
        people = [t for t in tracks if t.class_label == 0]

        proximity_thresh = self.rules.get("proximity_threshold", 120.0)
        time_thresh_ms = self.rules.get("abandoned_time_threshold_ms", 30000)

        events = []

        for bag in bags:
            # 1. Verify if bag is stationary
            if not self._is_stationary(bag):
                # Reset metadata if object starts moving again
                if "stationary_since" in bag.metadata:
                    bag.metadata.clear()
                continue

            bag_center = self._get_track_center(bag)
            bag_meta = bag.metadata

            # 2. Record when the bag first became stationary
            if "stationary_since" not in bag_meta:
                bag_meta["stationary_since"] = timestamp_ms

            # 3. Associate owner if not already done
            if "owner_track_id" not in bag_meta:
                # Find the closest person
                closest_person = None
                min_dist = float("inf")
                
                for person in people:
                    person_center = self._get_track_center(person)
                    dist = float(np.linalg.norm(bag_center - person_center))
                    if dist < min_dist:
                        min_dist = dist
                        closest_person = person

                if closest_person is not None and min_dist <= proximity_thresh:
                    bag_meta["owner_track_id"] = closest_person.track_id
                    logger.info(
                        "Associated owner track %d with stationary object %d (dist %.1fpx)",
                        closest_person.track_id,
                        bag.track_id,
                        min_dist,
                    )
                else:
                    # No owner found nearby when it became stationary
                    # Could have been placed prior to camera coverage, or owner already walked away
                    bag_meta["owner_track_id"] = -1

            # 4. Check owner proximity and if any other person is close
            owner_id = bag_meta["owner_track_id"]
            owner_present = False
            bystander_present = False

            for person in people:
                person_center = self._get_track_center(person)
                dist = float(np.linalg.norm(bag_center - person_center))
                
                if dist <= proximity_thresh:
                    if person.track_id == owner_id:
                        owner_present = True
                    else:
                        bystander_present = True

            # If owner is not present (or owner walked away) and no bystander is close
            is_unattended = (not owner_present) and (not bystander_present)

            if is_unattended:
                if "unattended_since" not in bag_meta:
                    bag_meta["unattended_since"] = timestamp_ms

                # Check duration of abandonment
                abandoned_duration = timestamp_ms - bag_meta["unattended_since"]
                if abandoned_duration >= time_thresh_ms:
                    # Trigger alert
                    zone_id = self.rules.get("zone_id")
                    event_type = "abandoned_object"

                    if self.should_suppress(event_type, zone_id, timestamp_ms):
                        continue

                    # Determine item name from class ID
                    class_names = {26: "backpack", 30: "handbag", 32: "suitcase"}
                    item_type = class_names.get(bag.class_label, "luggage")

                    events.append(
                        Event(
                            camera_id=self.camera_id,
                            event_type=event_type,
                            severity=self.rules.get("severity", "CRITICAL"),
                            timestamp_ms=timestamp_ms,
                            zone_id=zone_id,
                            metadata={
                                "item_type": item_type,
                                "object_track_id": bag.track_id,
                                "abandoned_duration_seconds": abandoned_duration / 1000.0,
                                "bounding_box": bag.bbox.tolist(),
                            },
                        )
                    )
            else:
                # Reset unattended timer if owner or bystander returns
                if "unattended_since" in bag_meta:
                    del bag_meta["unattended_since"]

        return events
