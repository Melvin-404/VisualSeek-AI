"""Unit tests, serialization checks, and benchmarks for ByteTrack multi-object tracking."""

import logging
import os
import sys
import unittest
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch

# Ensure packages/ai-pipeline/src is in sys.path
logger = logging.getLogger(__name__)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from tracking.bytetrack import ByteTracker, STrack, TrackState
from tracking.reid_model import OSNetReID
from tracking.track_manager import TrackManager
from tracking.trajectory import TrajectoryAnalyzer


class TestTrackingPipeline(unittest.TestCase):
    def setUp(self):
        # Set up a clean tracker instance for testing
        self.tracker = ByteTracker(
            track_thresh=0.5,
            high_thresh=0.6,
            match_thresh=0.8,
            max_time_lost_ms=1000,  # 1s max time lost for fast testing
            min_hits=2
        )
        self.dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def test_bytetrack_lifecycle(self):
        """Verify STrack transitions: TENTATIVE -> CONFIRMED -> LOST -> DELETED."""
        # 1. Start with high confidence detection. Track should be TENTATIVE (since min_hits=2)
        detections = np.array([[100, 100, 150, 150, 0.9, 0]])  # x1, y1, x2, y2, score, class
        active = self.tracker.update(detections, self.dummy_frame, timestamp_ms=100)
        
        self.assertEqual(len(active), 0)  # No confirmed tracks yet
        self.assertEqual(len(self.tracker.tracked_tracks), 1)
        track = self.tracker.tracked_tracks[0]
        self.assertEqual(track.state, TrackState.TENTATIVE)
        self.assertEqual(track.track_id, 1)

        # 2. Match in consecutive frame. State should become CONFIRMED
        detections2 = np.array([[101, 101, 151, 151, 0.95, 0]])
        active = self.tracker.update(detections2, self.dummy_frame, timestamp_ms=200)
        
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].state, TrackState.CONFIRMED)
        self.assertEqual(active[0].track_id, 1)

        # 3. Missing detection. State should change to LOST
        active = self.tracker.update(np.empty((0, 6)), self.dummy_frame, timestamp_ms=300)
        self.assertEqual(len(active), 0)
        self.assertEqual(len(self.tracker.tracked_tracks), 0)
        self.assertEqual(len(self.tracker.lost_tracks), 1)
        self.assertEqual(self.tracker.lost_tracks[0].state, TrackState.LOST)

        # 4. Exceed time lost threshold. State should be deleted
        active = self.tracker.update(np.empty((0, 6)), self.dummy_frame, timestamp_ms=1500)
        self.assertEqual(len(self.tracker.lost_tracks), 0)  # Purged from lost tracks

    def test_low_score_association(self):
        """Verify matching of low-score detections to active tracks (occlusion recovery)."""
        # Confirm a track first
        self.tracker.update(np.array([[100, 100, 150, 150, 0.9, 0]]), self.dummy_frame, timestamp_ms=100)
        self.tracker.update(np.array([[101, 101, 151, 151, 0.9, 0]]), self.dummy_frame, timestamp_ms=200)
        
        # Present a low-score detection (score=0.3, below track_thresh=0.5 but above 0.1)
        low_score_dets = np.array([[102, 102, 152, 152, 0.3, 0]])
        active = self.tracker.update(low_score_dets, self.dummy_frame, timestamp_ms=300)
        
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].track_id, 1)
        self.assertAlmostEqual(active[0].bbox[0], 102.0)

    def test_reid_occlusion_recovery(self):
        """Verify track recovery via ReID cosine similarity matching when IoU is zero."""
        # Setup mock ReID features
        feature1 = np.zeros(512, dtype=np.float32)
        feature1[10] = 1.0  # mock L2 normalized feature
        
        # Mock ReID model
        mock_reid = MagicMock()
        mock_reid.extract_embeddings.return_value = np.expand_dims(feature1, axis=0)

        # Confirm a track
        self.tracker.update(np.array([[100, 100, 150, 150, 0.9, 0]]), self.dummy_frame, timestamp_ms=100, reid_model=mock_reid)
        self.tracker.update(np.array([[101, 101, 151, 151, 0.9, 0]]), self.dummy_frame, timestamp_ms=200, reid_model=mock_reid)

        # Make track lost
        self.tracker.update(np.empty((0, 6)), self.dummy_frame, timestamp_ms=300, reid_model=mock_reid)
        self.assertEqual(self.tracker.lost_tracks[0].state, TrackState.LOST)

        # Re-detect at a distant position (IoU = 0) with highly similar feature
        new_dets = np.array([[400, 400, 450, 450, 0.9, 0]])  # distant box
        active = self.tracker.update(new_dets, self.dummy_frame, timestamp_ms=400, reid_model=mock_reid)

        # Track should be recovered with track ID 1
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].track_id, 1)
        self.assertEqual(active[0].state, TrackState.CONFIRMED)
        self.assertAlmostEqual(active[0].bbox[0], 400.0)

    def test_dwell_time_and_alerts(self):
        """Test dwell time accuracy and class-specific alert triggers."""
        # Set up a track spanning 5 seconds
        track = STrack(bbox=[100, 100, 200, 200], score=0.8, class_label=0, timestamp_ms=1000)
        track.track_id = 42
        track.state = TrackState.CONFIRMED
        
        # Update track at later timestamp
        new_det = STrack(bbox=[102, 102, 202, 202], score=0.85, class_label=0, timestamp_ms=6000)
        track.update(new_det, timestamp_ms=6000)

        analyzer = TrajectoryAnalyzer(dwell_thresholds={"person": 3.0, "vehicle": 10.0})

        # Calculate dwell time
        dwell = analyzer.calculate_dwell_time(track)
        # 6000ms - 1000ms = 5000ms = 5.0 seconds
        self.assertAlmostEqual(dwell, 5.0)

        # Test loitering alerts
        # 1. Person: dwell time 5.0s > threshold 3.0s -> True (Loitering alert)
        is_suspicious, dt, thresh = analyzer.check_suspicious_dwell(track, "person")
        self.assertTrue(is_suspicious)
        self.assertAlmostEqual(dt, 5.0)
        self.assertAlmostEqual(thresh, 3.0)

        # 2. Car (vehicle): dwell time 5.0s < threshold 10.0s -> False
        is_suspicious, dt, thresh = analyzer.check_suspicious_dwell(track, "car")
        self.assertFalse(is_suspicious)
        self.assertAlmostEqual(thresh, 10.0)

    def test_anonymization_blur(self):
        """Verify Gaussian face blur anonymizes target regions while keeping background intact."""
        manager = TrackManager()
        
        # Create a clean image: white background
        img = np.ones((200, 200, 3), dtype=np.uint8) * 255
        
        # Draw a solid black square inside head region to detect modification
        # BBox of person: [50, 50, 150, 180]
        # Fallback geometric head region: top 20% of box -> y range [50, 76]
        img[50:75, 60:140] = 0

        track = STrack(bbox=[50, 50, 150, 180], score=0.9, class_label=0, timestamp_ms=100)
        track.track_id = 1
        track.state = TrackState.CONFIRMED

        anonymized = manager.anonymize_frame(img, [track])

        # Verify pixels in head region are modified/blurred (no longer solid 0 or 255)
        head_pixels_original = img[55:70, 70:120]
        head_pixels_anonymized = anonymized[55:70, 70:120]
        
        self.assertFalse(np.array_equal(head_pixels_original, head_pixels_anonymized))
        
        # Verify pixels outside the person bounding box are completely unchanged
        bg_original = img[0:40, 0:40]
        bg_anonymized = anonymized[0:40, 0:40]
        self.assertTrue(np.array_equal(bg_original, bg_anonymized))

    def test_checkpoint_serialization(self):
        """Verify tracker state dictionary serialization and restore is lossless."""
        manager = TrackManager()

        # Generate mock detections and update camera
        dets = np.array([[100, 100, 150, 150, 0.9, 0], [300, 200, 350, 250, 0.85, 2]])
        manager.update_camera_tracker("cam_1", dets, self.dummy_frame, timestamp_ms=1000)

        # Make one confirmed
        manager.update_camera_tracker("cam_1", dets, self.dummy_frame, timestamp_ms=1100)

        # Save snapshot
        snapshot = manager.get_snapshot()
        self.assertIn("timestamp", snapshot)
        self.assertIn("trackers", snapshot)
        self.assertIn("cam_1", snapshot["trackers"])

        # Load snapshot into new manager
        manager2 = TrackManager()
        manager2.load_snapshot(snapshot)

        # Verify restored state
        self.assertIn("cam_1", manager2.trackers)
        t1 = manager.trackers["cam_1"]
        t2 = manager2.trackers["cam_1"]

        self.assertEqual(t1.frame_id, t2.frame_id)
        self.assertEqual(t1.next_track_id, t2.next_track_id)
        self.assertEqual(len(t1.tracked_tracks), len(t2.tracked_tracks))
        
        for tr1, tr2 in zip(t1.tracked_tracks, t2.tracked_tracks):
            self.assertEqual(tr1.track_id, tr2.track_id)
            self.assertEqual(tr1.state, tr2.state)
            self.assertTrue(np.array_equal(tr1.bbox, tr2.bbox))
            self.assertEqual(tr1.first_seen, tr2.first_seen)
            self.assertEqual(tr1.last_seen, tr2.last_seen)

    def test_gdpr_retention_cleanup(self):
        """Verify 30-day GDPR retention cleanup simulation executes without crash."""
        manager = TrackManager()
        deleted_count = manager.cleanup_expired_tracks(retention_days=30)
        self.assertGreaterEqual(deleted_count, 0)

    def test_stress_tracking_64_cameras(self):
        # Use mock ReID during stress test to bypass slow CPU ResNet-18 feature extraction
        mock_reid = MagicMock()
        mock_reid.extract_embeddings.side_effect = lambda frame, bboxes: np.random.randn(len(bboxes), 512).astype(np.float32)
        manager = TrackManager(reid_model=mock_reid)
        
        num_cameras = 64
        num_tracks_per_camera = 50

        import time
        start_time = time.perf_counter()

        for c in range(num_cameras):
            camera_id = f"cam_{c}"
            
            # Generate 50 unique bounding boxes
            boxes = []
            for t in range(num_tracks_per_camera):
                x = t * 10
                y = t * 8
                boxes.append([x, y, x + 50, y + 50, 0.85, 0])
            
            dets = np.array(boxes, dtype=np.float32)
            # Run tracker update
            tracks = manager.update_camera_tracker(camera_id, dets, self.dummy_frame, timestamp_ms=1000)
            
            self.assertEqual(len(tracks), 0)  # first frame -> all tentative because min_hits=2
            
            # Run second frame to confirm
            tracks_confirmed = manager.update_camera_tracker(camera_id, dets, self.dummy_frame, timestamp_ms=1100)
            self.assertEqual(len(tracks_confirmed), num_tracks_per_camera)

        elapsed = time.perf_counter() - start_time
        logger.info("[Stress Test] 64 cameras x 50 tracks processed in %.3fs", elapsed)
        
        # Verify execution is fast (< 2.0s for the whole stress batch)
        self.assertLess(elapsed, 2.0)
