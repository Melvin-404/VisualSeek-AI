"""Unit tests and benchmarks for the frame preprocessing pipeline."""

import logging
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
import torch

# Ensure packages/ai-pipeline/src is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from preprocessing.batch_assembler import BatchAssembler
from preprocessing.dali_pipeline import PreprocessingPipelineManager, pytorch_letterbox, pytorch_normalize
from preprocessing.deduplicator import FrameDeduplicator
from preprocessing.frame_extractor import GPUFrameExtractor, numpy_ssim, pytorch_ssim


def create_dummy_video(filename: str, width: int = 320, height: int = 240, fps: int = 30, num_frames: int = 30) -> None:
    """Create a dummy MP4 video file with simulated motion."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(filename, fourcc, fps, (width, height))
    for i in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Add text
        cv2.putText(frame, f"Frame {i}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        # Add a moving green block to simulate motion
        x = (i * 8) % (width - 50)
        frame[100:150, x : x + 50] = [0, 255, 0]
        writer.write(frame)
    writer.release()


class TestFrameExtractor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.video_filename = "test_motion.mp4"
        create_dummy_video(cls.video_filename)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.video_filename):
            os.remove(cls.video_filename)

    def test_frame_extractor_decodes_frames(self):
        extractor = GPUFrameExtractor(self.video_filename, enable_gpu=False)
        frames = list(extractor.extract_frames(motion_threshold=1.0))  # 1.0 means no motion filtering (keep all)
        
        self.assertGreater(len(frames), 0)
        first_frame, metadata = frames[0]
        self.assertEqual(first_frame.shape, (240, 320, 3))
        self.assertEqual(metadata["frame_number"], 1)
        self.assertEqual(metadata["timestamp_ms"], 0)

    def test_ssim_motion_detection(self):
        # Create identical frames (SSIM should be 1.0)
        frame1 = np.ones((100, 100, 3), dtype=np.uint8) * 128
        frame2 = np.ones((100, 100, 3), dtype=np.uint8) * 128
        
        score_np = numpy_ssim(frame1, frame2)
        self.assertAlmostEqual(score_np, 1.0, places=4)

        # Create different frames (SSIM should be lower)
        frame3 = np.ones((100, 100, 3), dtype=np.uint8) * 50
        score_diff = numpy_ssim(frame1, frame3)
        self.assertLess(score_diff, 0.9)

        # Test PyTorch version if CUDA is available, or run on CPU
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        t1 = torch.from_numpy(frame1).permute(2, 0, 1).to(device)
        t2 = torch.from_numpy(frame2).permute(2, 0, 1).to(device)
        score_torch = pytorch_ssim(t1, t2)
        self.assertAlmostEqual(score_torch, 1.0, places=4)


class TestPreprocessingPipeline(unittest.TestCase):
    def test_dali_letterbox_output_shape(self):
        # Create an input frame [C, H, W]
        frame = torch.randint(0, 256, (3, 200, 400), dtype=torch.uint8)
        
        # Preprocess using letterbox
        target_size = (640, 640)
        processed = pytorch_letterbox(frame, target_size)
        
        # Check shapes
        self.assertEqual(processed.shape, (3, 640, 640))
        # Check value scaling (should be normalise-ready [0.0, 1.0])
        self.assertLessEqual(processed.max().item(), 1.0)
        self.assertGreaterEqual(processed.min().item(), 0.0)

    def test_pipeline_manager(self):
        manager = PreprocessingPipelineManager(target_size=(640, 640), enable_gpu=False)
        frames = [
            np.zeros((480, 640, 3), dtype=np.uint8),
            np.ones((480, 640, 3), dtype=np.uint8) * 255
        ]
        batch = manager.preprocess(frames)
        self.assertEqual(batch.shape, (2, 3, 640, 640))


class TestFrameDeduplicator(unittest.TestCase):
    def test_phash_deduplication(self):
        deduplicator = FrameDeduplicator(phash_threshold=4, window_size=10, enable_gpu=False)

        # 1. Create a base frame
        frame1 = np.zeros((200, 200, 3), dtype=np.uint8)
        cv2.putText(frame1, "VisionQuery", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        # Calculate base hash
        hash1 = deduplicator.compute_phash(frame1)
        self.assertIsNotNone(hash1)

        # 2. Test exact duplicate
        is_dup = deduplicator.is_duplicate(frame1)
        self.assertFalse(is_dup)  # first time seeing it, shouldn't be marked duplicate

        is_dup_second = deduplicator.is_duplicate(frame1)
        self.assertTrue(is_dup_second)  # second time, is a duplicate!

        # 3. Test slightly modified frame (should catch as duplicate if Hamming dist <= 4)
        frame_modified = frame1.copy()
        # Add minor noise
        frame_modified[5:10, 5:10] = [2, 2, 2]
        is_dup_modified = deduplicator.is_duplicate(frame_modified)
        self.assertTrue(is_dup_modified)

        # 4. Test completely different frame (should NOT be duplicate)
        frame2 = np.zeros((200, 200, 3), dtype=np.uint8)
        cv2.putText(frame2, "Different Text", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        is_dup_diff = deduplicator.is_duplicate(frame2)
        self.assertFalse(is_dup_diff)


class TestBatchAssembler(unittest.TestCase):
    def test_batch_assembler_pinning(self):
        assembler = BatchAssembler(batch_size=2, pin_memory=True)
        
        t1 = torch.zeros((3, 640, 640), dtype=torch.float32)
        t2 = torch.ones((3, 640, 640), dtype=torch.float32)
        
        assembler.add_frame(t1, {"frame_number": 1, "timestamp_ms": 100})
        self.assertFalse(assembler.is_ready())
        
        assembler.add_frame(t2, {"frame_number": 2, "timestamp_ms": 200})
        self.assertTrue(assembler.is_ready())
        
        batch_tensor, metadata, stats = assembler.assemble_batch()
        self.assertEqual(batch_tensor.shape, (2, 3, 640, 640))
        self.assertEqual(len(metadata), 2)
        self.assertIn("fps", stats)
        self.assertIn("assembly_latency_ms", stats)
        
        # If CUDA is available and pin_memory was enabled, verify it is pinned
        if torch.cuda.is_available():
            self.assertTrue(batch_tensor.is_pinned())


class TestPreprocessingBenchmark(unittest.TestCase):
    def test_benchmark_throughput(self):
        """Benchmark the preprocessing pipeline to estimate frame throughput (FPS)."""
        manager = PreprocessingPipelineManager(target_size=(640, 640), enable_gpu=torch.cuda.is_available())
        
        # Create a mock batch of 32 frames
        frame_shape = (1080, 1920, 3)  # 1080p frames
        frames = [np.random.randint(0, 256, frame_shape, dtype=np.uint8) for _ in range(32)]
        
        # Warm-up
        for _ in range(2):
            _ = manager.preprocess(frames)
            
        # Benchmark loop
        iterations = 5
        start_time = time.perf_counter()
        
        for _ in range(iterations):
            _ = manager.preprocess(frames)
            
        end_time = time.perf_counter()
        elapsed = end_time - start_time
        total_frames = iterations * len(frames)
        fps = total_frames / elapsed
        
        print(f"\n[Benchmark] Throughput: {fps:.2f} frames/second (Elapsed: {elapsed:.3f}s for {total_frames} frames)")
        
        # If running on H200 / GPU, assert throughput > 1000 FPS
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0).lower()
            if "h200" in device_name or "a100" in device_name or "rtx" in device_name:
                self.assertGreater(fps, 1000.0, f"Throughput on GPU ({fps:.2f} FPS) is below the 1000 FPS requirement.")
        else:
            logging.warning("Benchmarking on CPU. Throughput requirement of 1000 FPS is not enforced.")
