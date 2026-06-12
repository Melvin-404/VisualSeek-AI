"""Unit tests for the GPU-accelerated video ingestion pipeline.

Tests use mocks for cv2, minio, and database operations.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure packages/ai-pipeline/src is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from ingestion.config import IngestionConfig
from ingestion.health_monitor import HealthStatus, StreamHealthMonitor
from ingestion.quality_check import FrameQualityChecker
from ingestion.rtsp_worker import RTSPIngestionWorker
from ingestion.segmenter import SegmentResult, VideoSegmenter
from ingestion.storage import MinIOVideoStorage


class TestVideoSegmenter(unittest.TestCase):
    def setUp(self):
        self.config = IngestionConfig()
        self.config.segment.duration_s = 2.0  # short duration for testing
        self.config.segment.overlap_s = 0.5
        self.config.segment.temp_dir = "test-vq-segments"
        self.segmenter = VideoSegmenter("test_cam", self.config)

    def tearDown(self):
        import shutil
        if os.path.exists("test-vq-segments"):
            shutil.rmtree("test-vq-segments")

    @patch("cv2.VideoWriter")
    def test_segmenter_creates_segments_at_duration(self, mock_video_writer):
        # Mock VideoWriter
        mock_writer_inst = MagicMock()
        mock_writer_inst.isOpened.return_value = True
        mock_video_writer.return_value = mock_writer_inst

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Add frames spanning 2 seconds
        # 10 frames at 5 FPS
        res = None
        for i in range(11):
            res = self.segmenter.add_frame(frame, float(i) * 0.2)
            if res:
                break
        
        self.assertIsNotNone(res)
        self.assertEqual(res.camera_id, "test_cam")
        self.assertEqual(res.frame_count, 11)
        mock_video_writer.assert_called_once()

    def test_segmenter_overlap_frames_retained(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Add frames spanning 2 seconds
        # Timestamps: 0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0
        # Overlap threshold is last 0.5s: 1.5 to 2.0
        # Overlap frames: 1.6, 1.8, 2.0 (3 frames)
        for i in range(11):
            self.segmenter.add_frame(frame, float(i) * 0.2)
            
        with patch("cv2.VideoWriter") as mock_video_writer:
            mock_writer_inst = MagicMock()
            mock_writer_inst.isOpened.return_value = True
            mock_video_writer.return_value = mock_writer_inst
            
            # Finalize segment should trigger, and buffer should retain the last 3 frames
            res = self.segmenter._finalize_segment()
            
            # The buffer should now contain the overlap frames (timestamps 1.6, 1.8, 2.0)
            self.assertEqual(len(self.segmenter._frame_buffer), 3)
            self.assertEqual(self.segmenter._frame_buffer[0][1], 1.6)
            self.assertEqual(self.segmenter._frame_buffer[-1][1], 2.0)


class TestFrameQualityChecker(unittest.TestCase):
    def setUp(self):
        self.config = IngestionConfig()
        self.config.quality.blur_threshold = 10.0
        self.config.quality.darkness_threshold = 10.0
        self.config.quality.frozen_threshold = 0.98
        self.checker = FrameQualityChecker(self.config)

    @patch("cv2.Laplacian")
    def test_quality_checker_detects_blur(self, mock_laplacian):
        # Mock low variance for blurry image
        mock_laplacian.return_value = MagicMock(var=MagicMock(return_value=5.0))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        is_blurry, score = self.checker.is_blurry(frame)
        self.assertTrue(is_blurry)
        self.assertEqual(score, 5.0)

    def test_quality_checker_detects_darkness(self):
        # Black frame is dark
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        is_dark, score = self.checker.is_dark(frame)
        self.assertTrue(is_dark)
        self.assertEqual(score, 0.0)

    @patch("cv2.matchTemplate")
    def test_quality_checker_detects_frozen(self, mock_match):
        # Mock similarity score > 0.98
        mock_match.return_value = np.array([[0.99]], dtype=np.float32)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        prev = np.zeros((480, 640), dtype=np.uint8)
        
        is_frozen, score = self.checker.is_frozen(frame, prev)
        self.assertTrue(is_frozen)
        self.assertAlmostEqual(score, 0.99, places=5)


class TestMinIOVideoStorage(unittest.TestCase):
    @patch("ingestion.storage.Minio")
    def test_minio_upload_with_retry(self, mock_minio):
        # Mock client behavior
        mock_client = MagicMock()
        mock_minio.return_value = mock_client
        
        # Test retry logic: fail first, succeed second
        storage = MinIOVideoStorage()
        
        segment = SegmentResult(
            file_path="dummy.mp4",
            segment_id="test_id",
            camera_id="cam_1",
            start_time=1700000000.0,
            end_time=1700000030.0,
            duration_ms=30000,
            fps=30.0,
            resolution="1920x1080",
            codec="mp4v",
            frame_count=900,
            file_size_bytes=100000
        )
        
        with patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=100000):
            
            # Fail first, then succeed
            mock_client.fput_object.side_effect = [Exception("Temporary S3 error"), None]
            
            key = storage.upload_with_retry(segment, "org_123", max_retries=2)
            self.assertEqual(mock_client.fput_object.call_count, 2)
            self.assertIn("org_123/cam_1/2023/11/14/test_id.mp4", key)

    @patch("ingestion.storage.Minio")
    def test_minio_s3_key_format(self, mock_minio):
        mock_client = MagicMock()
        mock_minio.return_value = mock_client
        storage = MinIOVideoStorage()
        
        segment = SegmentResult(
            file_path="dummy.mp4",
            segment_id="seg_abc",
            camera_id="cam_xyz",
            start_time=1718064000.0,  # 2024-06-11 00:00:00 UTC
            end_time=1718064030.0,
            duration_ms=30000,
            fps=30.0,
            resolution="1280x720",
            codec="mp4v",
            frame_count=900,
            file_size_bytes=50000
        )
        
        with patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=50000):
            
            key = storage.upload_segment(segment, "org_999")
            self.assertEqual(key, "org_999/cam_xyz/2024/06/11/seg_abc.mp4")


class TestStreamHealthMonitor(unittest.TestCase):
    def test_health_monitor_status_transitions(self):
        monitor = StreamHealthMonitor()
        
        # Initial offline status
        health = monitor.get_health("cam_1")
        self.assertEqual(health.status, HealthStatus.OFFLINE)
        
        # Transition to healthy
        health.target_fps = 2.0  # lower target FPS so rolling FPS qualifies as healthy
        for _ in range(5):
            monitor.record_frame("cam_1")
            
        health = monitor.get_health("cam_1")
        self.assertEqual(health.status, HealthStatus.HEALTHY)
        
        # Transition to degraded on errors
        for _ in range(6):
            monitor.record_error("cam_1", "Frame read failed")
            
        health = monitor.get_health("cam_1")
        self.assertEqual(health.status, HealthStatus.DEGRADED)
        
        # Transition to critical on many errors
        for _ in range(15):
            monitor.record_error("cam_1", "Frame read failed")
            
        health = monitor.get_health("cam_1")
        self.assertEqual(health.status, HealthStatus.CRITICAL)


class TestRTSPIngestionWorker(unittest.TestCase):
    @patch("ingestion.rtsp_worker.cv2.VideoCapture")
    @patch("ingestion.rtsp_worker.StreamHealthMonitor")
    @patch("ingestion.rtsp_worker.FrameQualityChecker")
    @patch("ingestion.rtsp_worker.VideoSegmenter")
    def test_rtsp_worker_reconnect_backoff(self, mock_segmenter, mock_quality, mock_health, mock_capture):
        # Setup mock capture to fail to open
        mock_cap_inst = MagicMock()
        mock_cap_inst.isOpened.return_value = False
        mock_capture.return_value = mock_cap_inst
        
        config = IngestionConfig()
        config.rtsp.reconnect_base_delay_s = 0.01
        config.rtsp.reconnect_max_delay_s = 0.05
        
        worker = RTSPIngestionWorker("cam_reconnect", "rtsp://dummy", "org_1", config)
        
        with patch.object(worker, "connect", return_value=False) as mock_connect, \
             patch.object(worker._shutdown_event, "wait") as mock_wait:
            
            # If shutdown event is set, reconnect should stop
            worker._shutdown_event.set()
            res = worker.reconnect()
            self.assertFalse(res)
            
            # Reset shutdown and check wait delay matches exponential backoff
            worker._shutdown_event.clear()
            
            # Attempt 1: reconnect_base_delay_s * 2^0 = 0.01s
            worker._reconnect_attempt = 0
            worker.reconnect()
            mock_wait.assert_any_call(timeout=0.01)
            
            # Attempt 2: reconnect_base_delay_s * 2^1 = 0.02s
            worker.reconnect()
            mock_wait.assert_any_call(timeout=0.02)
