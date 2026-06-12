"""Base event detector definition and immutable Event model with deduplication."""

from dataclasses import dataclass, field
import logging
from typing import Dict, List, Optional, Tuple
import uuid

import numpy as np

from tracking.bytetrack import STrack

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    """Immutable representation of a security-relevant event."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    camera_id: str = ""
    event_type: str = ""  # e.g., "crowd_gathering", "perimeter_breach"
    severity: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    timestamp_ms: int = 0
    zone_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class EventDetector:
    """Base detector class providing rule configuration and 30-second window event deduplication."""

    def __init__(self, camera_id: str):
        """Initialize the event detector."""
        self.camera_id = camera_id
        self.rules: dict = {}
        # History format: [(event_type, zone_id, timestamp_ms)]
        self._emitted_history: List[Tuple[str, Optional[str], int]] = []

    def configure(self, rules: dict) -> None:
        """Configure detector sensitivity, thresholds, and zones."""
        self.rules.update(rules)

    def should_suppress(
        self, event_type: str, zone_id: Optional[str], timestamp_ms: int, window_ms: int = 30000
    ) -> bool:
        """Deduplicate events: suppress if identical event was emitted in the same zone within window_ms."""
        # Remove history older than sliding window
        cutoff = timestamp_ms - window_ms
        self._emitted_history = [item for item in self._emitted_history if item[2] >= cutoff]

        # Check for matching active duplicates
        for hist_type, hist_zone, hist_ts in self._emitted_history:
            if hist_type == event_type and hist_zone == zone_id:
                return True

        # Register new event in history
        self._emitted_history.append((event_type, zone_id, timestamp_ms))
        return False

    def detect(self, tracks: List[STrack], frame: np.ndarray, timestamp_ms: int) -> List[Event]:
        """Core detection run to be implemented by child classes.

        Args:
            tracks: List of active confirmed tracks.
            frame: Raw image frame.
            timestamp_ms: Current timestamp in milliseconds.
        """
        raise NotImplementedError("Subclasses must implement the detect method.")
