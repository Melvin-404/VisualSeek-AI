"""Unit tests for ML-based and rule-based event detection and publishing."""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock

import numpy as np
import pytest
import shapely.geometry as sg

# Ensure packages/ai-pipeline/src is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from events.abandoned_object import AbandonedObjectDetector
from events.base_detector import Event, EventDetector
from events.crowd_detector import CrowdGatheringDetector
from events.event_publisher import EventPublisher
from events.fight_detector import FightDetector, SmokeFireDetector
from events.loitering import LoiteringDetector
from events.perimeter import PerimeterBreachDetector, WrongDirectionDetector
from tracking.bytetrack import STrack


class TestEventEngine(unittest.TestCase):
    def setUp(self):
        self.dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def test_crowd_gathering(self):
        """Test crowd gathering alert when > 10 people cluster closely together."""
        detector = CrowdGatheringDetector(camera_id="cam_1")
        detector.configure({"count_threshold": 10, "density_threshold": 100.0})

        # Synthesize 12 person tracks close to each other
        tracks = []
        for i in range(12):
            # Centered around (150 + i * 4, 150)
            bbox = [100 + i * 4, 100, 200 + i * 4, 200]
            track = STrack(bbox=bbox, score=0.9, class_label=0, timestamp_ms=1000)
            track.track_id = i + 1
            # Confirm them
            track.hits = 5
            tracks.append(track)

        events = detector.detect(tracks, self.dummy_frame, timestamp_ms=1000)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "crowd_gathering")
        self.assertEqual(events[0].metadata["people_count"], 12)

    def test_abandoned_object(self):
        """Test abandoned object triggers alert when owner walks away for > 30s."""
        detector = AbandonedObjectDetector(camera_id="cam_1")
        # Configure small threshold for fast tests
        detector.configure({"abandoned_time_threshold_ms": 1000, "proximity_threshold": 100.0})

        # 1. Create a suitcase track (class 32)
        suitcase = STrack(bbox=[200, 200, 250, 250], score=0.85, class_label=32, timestamp_ms=1000)
        suitcase.track_id = 99
        # Stationary suitcase simulation in chronological order
        suitcase.history = [
            (900, np.array([200, 200, 250, 250], dtype=np.float32)),
            (950, np.array([200, 200, 250, 250], dtype=np.float32)),
            (1000, np.array([200, 200, 250, 250], dtype=np.float32)),
        ]

        # 2. Create a person track (class 0) nearby
        owner = STrack(bbox=[210, 210, 260, 290], score=0.9, class_label=0, timestamp_ms=1000)
        owner.track_id = 1
        owner.hits = 5

        # Update at t=1000. Object should associate owner track ID 1. No alert yet.
        tracks = [suitcase, owner]
        events = detector.detect(tracks, self.dummy_frame, timestamp_ms=1000)
        self.assertEqual(len(events), 0)
        self.assertEqual(suitcase.metadata["owner_track_id"], 1)

        # 3. Owner walks away in subsequent frame
        owner_far = STrack(bbox=[500, 500, 550, 580], score=0.9, class_label=0, timestamp_ms=1100)
        owner_far.track_id = 1
        owner_far.hits = 6

        # Update at t=1100. Unattended timer starts.
        tracks = [suitcase, owner_far]
        events = detector.detect(tracks, self.dummy_frame, timestamp_ms=1100)
        self.assertEqual(len(events), 0)
        self.assertIn("unattended_since", suitcase.metadata)

        # 4. Trigger alert after 1200ms unattended duration (> 1000ms threshold)
        events = detector.detect(tracks, self.dummy_frame, timestamp_ms=2300)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "abandoned_object")
        self.assertEqual(events[0].metadata["item_type"], "suitcase")
        self.assertEqual(events[0].metadata["object_track_id"], 99)

    def test_loitering_zone(self):
        """Test loitering alert triggers when track dwells in a polygon zone."""
        detector = LoiteringDetector(camera_id="cam_1")
        
        # Configure a polygon zone (100x100 square)
        detector.configure({
            "dwell_threshold_ms": 1000,
            "zones": {
                "lounge_area": [(0, 0), (100, 0), (100, 100), (0, 100)]
            }
        })

        # Person inside the zone
        person = STrack(bbox=[40, 40, 60, 60], score=0.95, class_label=0, timestamp_ms=1000)
        person.track_id = 7
        person.hits = 5

        # First check (t=1000) -> Entry recorded
        events = detector.detect([person], self.dummy_frame, timestamp_ms=1000)
        self.assertEqual(len(events), 0)

        # Dwell inside the zone (reuse the same track object, update timestamp)
        person.last_seen = 2200

        # Second check (t=2200) -> 1.2s dwell (> 1.0s threshold) -> Alert
        events = detector.detect([person], self.dummy_frame, timestamp_ms=2200)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "loitering")
        self.assertEqual(events[0].zone_id, "lounge_area")

    def test_perimeter_breach(self):
        """Test perimeter breach when a track crosses a virtual tripwire."""
        detector = PerimeterBreachDetector(camera_id="cam_1")
        
        # Configure tripwire line at x=100
        detector.configure({
            "lines": {
                "gate_tripwire": [(100, 0), (100, 200)]
            }
        })

        # Synthesize a track crossing from x=90 to x=110 chronologically
        track = STrack(bbox=[85, 50, 95, 70], score=0.9, class_label=0, timestamp_ms=1000)
        track.track_id = 3
        # Add new point at t=1100 crossing to x=110
        track.bbox = np.array([105, 50, 115, 70], dtype=np.float32)
        track.history.append((1100, track.bbox.copy()))
        track.last_seen = 1100

        events = detector.detect([track], self.dummy_frame, timestamp_ms=1100)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "perimeter_breach")
        self.assertEqual(events[0].zone_id, "gate_tripwire")
        self.assertEqual(events[0].metadata["breach_type"], "tripwire_crossing")

    def test_wrong_direction(self):
        """Test wrong direction flow when moving vector opposes allowed flow direction."""
        detector = WrongDirectionDetector(camera_id="cam_1")
        
        # Allowed flow: moving right (dx=1.0, dy=0.0)
        detector.configure({
            "allowed_direction": [1.0, 0.0],
            "angle_threshold": 90.0,
            "history_frames": 3
        })

        # Synthesize a track moving left (opposite flow) in chronological order
        track = STrack(bbox=[200, 50, 220, 70], score=0.9, class_label=0, timestamp_ms=1000)
        track.track_id = 5
        track.history.append((1100, np.array([170, 50, 190, 70], dtype=np.float32)))
        track.history.append((1200, np.array([130, 50, 150, 70], dtype=np.float32)))
        track.bbox = np.array([100, 50, 120, 70], dtype=np.float32)
        track.history.append((1300, track.bbox.copy()))
        track.last_seen = 1300

        events = detector.detect([track], self.dummy_frame, timestamp_ms=1300)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "wrong_direction")

    def test_fight_and_smoke(self):
        """Test physical fight trajectory scuffles and smoke/fire fine-tune triggers."""
        # 1. Fight Detector
        fight_detector = FightDetector(camera_id="cam_1")
        fight_detector.configure({"acceleration_threshold": 5.0, "overlap_threshold": 0.2})

        # Synthesize overlapping, rapidly moving person tracks in chronological order
        t1 = STrack(bbox=[100, 100, 150, 150], score=0.9, class_label=0, timestamp_ms=1000)
        t1.track_id = 1
        t1.history.append((1100, np.array([90, 90, 140, 140], dtype=np.float32)))
        t1.bbox = np.array([120, 120, 170, 170], dtype=np.float32)
        t1.history.append((1200, t1.bbox.copy()))
        t1.last_seen = 1200

        t2 = STrack(bbox=[105, 105, 155, 155], score=0.9, class_label=0, timestamp_ms=1000)
        t2.track_id = 2
        t2.history.append((1100, np.array([125, 125, 175, 175], dtype=np.float32)))
        t2.bbox = np.array([95, 95, 145, 145], dtype=np.float32)
        t2.history.append((1200, t2.bbox.copy()))
        t2.last_seen = 1200

        events = fight_detector.detect([t1, t2], self.dummy_frame, timestamp_ms=1200)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "fight")

        # 2. Smoke/Fire Detector
        smoke_detector = SmokeFireDetector(camera_id="cam_1")
        # Verify no event by default
        events = smoke_detector.detect([], self.dummy_frame, timestamp_ms=1000)
        self.assertEqual(len(events), 0)

        # Trigger mock smoke alert
        smoke_detector.configure({"mock_trigger": True})
        events = smoke_detector.detect([], self.dummy_frame, timestamp_ms=1000)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "smoke_fire")

    def test_event_deduplication(self):
        """Verify duplicate events are suppressed within a 30-second window."""
        detector = CrowdGatheringDetector(camera_id="cam_1")
        detector.configure({"count_threshold": 2, "density_threshold": 100.0, "zone_id": "lobby"})

        t1 = STrack(bbox=[100, 100, 120, 120], score=0.9, class_label=0, timestamp_ms=1000)
        t2 = STrack(bbox=[105, 105, 125, 125], score=0.9, class_label=0, timestamp_ms=1000)
        t1.hits = t2.hits = 5

        # 1. First trigger -> Emits event
        events = detector.detect([t1, t2], self.dummy_frame, timestamp_ms=1000)
        self.assertEqual(len(events), 1)

        # 2. Immediate second trigger -> Suppressed (0 events)
        events = detector.detect([t1, t2], self.dummy_frame, timestamp_ms=5000)  # 5s later
        self.assertEqual(len(events), 0)

        # 3. Third trigger after window -> Emits event (35s later)
        events = detector.detect([t1, t2], self.dummy_frame, timestamp_ms=36000)
        self.assertEqual(len(events), 1)

    def test_event_publisher_websocket(self):
        """Verify WebSocket emission callback is triggered and PII is redacted."""
        publisher = EventPublisher()
        
        callback_called = False
        received_payload = {}

        def ws_callback(msg):
            nonlocal callback_called, received_payload
            callback_called = True
            received_payload = json.loads(msg)

        publisher.subscribe_websocket(ws_callback)

        # Create an event containing PII in metadata
        event = Event(
            camera_id="cam_1",
            event_type="intruder",
            severity="CRITICAL",
            timestamp_ms=1000,
            metadata={
                "name": "Jane Doe",
                "biometrics_hash": "aef9123490",
                "object_speed": 12.5,
                "nested_pii": {
                    "identity_card": "ID-12345",
                    "safe_key": "safe_value"
                }
            }
        )

        publisher.publish(event)

        # Check callback execution
        self.assertTrue(callback_called)
        self.assertEqual(received_payload["event_type"], "intruder")
        
        # Verify GDPR PII Redaction
        meta = received_payload["metadata"]
        self.assertNotIn("name", meta)
        self.assertNotIn("biometrics_hash", meta)
        self.assertEqual(meta["object_speed"], 12.5)
        
        # Nested redaction checks
        self.assertNotIn("identity_card", meta["nested_pii"])
        self.assertEqual(meta["nested_pii"]["safe_key"], "safe_value")
