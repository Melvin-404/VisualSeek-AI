"""Unit tests, concurrency hot-swap verification, and benchmarks for YOLOv10 detection."""

import hashlib
import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

# Ensure packages/ai-pipeline/src is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from detection.calibration import YOLOEntropyCalibrator
from detection.config import DetectionConfig
from detection.model_registry import ModelRegistry
from detection.postprocessor import DetectionResult, Postprocessor, SURVEILLANCE_CLASSES
from detection.triton_client import TritonInferenceClient
from detection.yolo_engine import YOLOTensorRTEngine


class TestDetectionPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a dummy model file for testing integrity checks
        cls.dummy_model_path = "models/test_dummy_yolo.onnx"
        cls.dummy_engine_path = "models/test_dummy_yolo.engine"
        cls.calibration_cache = "models/test_dummy_calib.cache"

        os.makedirs("models", exist_ok=True)
        cls.dummy_content = b"fake-onnx-model-data-for-surveillance"
        with open(cls.dummy_model_path, "wb") as f:
            f.write(cls.dummy_content)

        cls.expected_sha256 = hashlib.sha256(cls.dummy_content).hexdigest()

        # Set up default configuration
        cls.config = DetectionConfig(
            model_name="yolov10x_test",
            model_path=cls.dummy_model_path,
            engine_path=cls.dummy_engine_path,
            calibration_cache_path=cls.calibration_cache,
            max_batch_size=64,
            enable_int8=True,
            enable_fp16=True,
            iou_threshold=0.45,
            confidence_thresholds={"person": 0.4, "vehicle": 0.5, "object": 0.3},
            triton_server_url="localhost:8001",
            enable_triton=False,
        )

    @classmethod
    def tearDownClass(cls):
        for path in [cls.dummy_model_path, cls.dummy_engine_path, cls.calibration_cache]:
            if os.path.exists(path):
                os.remove(path)

    def test_sha256_integrity_check(self):
        """Test SHA256 checksum and model registration verification."""
        registry = ModelRegistry(self.config)

        # Register with correct SHA256
        registry.register_model(
            model_name="correct_model",
            model_path=self.dummy_model_path,
            engine_path=self.dummy_engine_path,
            expected_sha256=self.expected_sha256,
        )
        self.assertTrue(registry.verify_integrity("correct_model"))

        # Register with wrong SHA256
        registry.register_model(
            model_name="corrupt_model",
            model_path=self.dummy_model_path,
            engine_path=self.dummy_engine_path,
            expected_sha256="wrong-sha256-hash-value-1234567890abcdef",
        )
        self.assertFalse(registry.verify_integrity("corrupt_model"))

        # Check non-existent model
        self.assertFalse(registry.verify_integrity("non_existent_model"))

    @patch("detection.yolo_engine.HAS_TRT", True)
    @patch("detection.yolo_engine.trt")
    def test_yolo_engine_compilation_and_load(self, mock_trt):
        """Test the TensorRT compilation and loading code paths using mocks."""
        # Setup mock TRT builder network and configurations
        mock_builder = MagicMock()
        mock_network = MagicMock()
        mock_parser = MagicMock()
        mock_builder_config = MagicMock()
        mock_profile = MagicMock()

        mock_trt.Builder.return_value = mock_builder
        mock_builder.create_network.return_value = mock_network
        mock_trt.OnnxParser.return_value = mock_parser
        mock_builder.create_builder_config.return_value = mock_builder_config
        mock_builder.create_optimization_profile.return_value = mock_profile

        # Mock ONNX parsing to succeed
        mock_parser.parse_from_file.return_value = True

        # Mock engine serialization and build
        mock_serialized_engine = b"compiled-serialized-trt-engine-data"
        mock_builder.build_serialized_network.return_value = mock_serialized_engine

        # Mock runtime deserialization
        mock_runtime = MagicMock()
        mock_trt.Runtime.return_value = mock_runtime
        mock_engine = MagicMock()
        mock_context = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = mock_engine
        mock_engine.create_execution_context.return_value = mock_context

        # Instantiate engine and test compilation
        engine = YOLOTensorRTEngine(self.config)
        calibration_frames = [np.zeros((3, 640, 640), dtype=np.uint8) for _ in range(10)]

        compilation_success = engine.compile_engine(calibration_data=calibration_frames)
        self.assertTrue(compilation_success)
        self.assertTrue(os.path.exists(self.dummy_engine_path))

        # Test engine loading
        load_success = engine.load_engine()
        self.assertTrue(load_success)
        self.assertEqual(engine.engine, mock_engine)
        self.assertEqual(engine.context, mock_context)

    def test_dynamic_batch_inference(self):
        """Test inference across multiple dynamic batch sizes."""
        engine = YOLOTensorRTEngine(self.config)
        engine.load_engine()  # loads fallback runner in local environment

        for batch_size in [1, 4, 16, 32, 64]:
            batch_tensor = torch.randn(batch_size, 3, 640, 640, dtype=torch.float32)
            raw_out = engine.execute_inference(batch_tensor)
            
            # Verify output shape [B, 300, 6]
            self.assertEqual(raw_out.shape, (batch_size, 300, 6))

        # Exceeding batch size should raise error
        with self.assertRaises(ValueError):
            large_batch = torch.randn(65, 3, 640, 640, dtype=torch.float32)
            engine.execute_inference(large_batch)

    def test_class_specific_thresholds(self):
        """Verify the class-specific confidence thresholds are correctly applied."""
        postprocessor = Postprocessor(self.config)

        # Construct raw output containing multiple mock detections
        # Format: [x1, y1, x2, y2, score, class_id]
        # Classes: 0 -> person (threshold 0.4), 2 -> car (threshold 0.5), 43 -> cup (object, threshold 0.3)
        raw_output = np.zeros((1, 6, 6), dtype=np.float32)
        raw_output[0, 0] = [100, 100, 200, 200, 0.45, 0.0]   # Person, score=0.45 -> KEEP
        raw_output[0, 1] = [100, 100, 200, 200, 0.35, 0.0]   # Person, score=0.35 -> FILTER
        raw_output[0, 2] = [300, 300, 400, 400, 0.55, 2.0]   # Car, score=0.55 -> KEEP
        raw_output[0, 3] = [300, 300, 400, 400, 0.45, 2.0]   # Car, score=0.45 -> FILTER
        raw_output[0, 4] = [500, 500, 600, 600, 0.35, 46.0]  # Cup (object), score=0.35 -> KEEP
        raw_output[0, 5] = [500, 500, 600, 600, 0.25, 46.0]  # Cup (object), score=0.25 -> FILTER

        results = postprocessor.postprocess(raw_output, [(640, 640)])[0]

        # Verify only 3 detections remain
        self.assertEqual(len(results), 3)

        # Check details of kept detections
        class_names = [r.class_name for r in results]
        self.assertIn("person", class_names)
        self.assertIn("car", class_names)
        self.assertIn("cup", class_names)

        for res in results:
            if res.class_name == "person":
                self.assertAlmostEqual(res.confidence, 0.45)
            elif res.class_name == "car":
                self.assertAlmostEqual(res.confidence, 0.55)
            elif res.class_name == "cup":
                self.assertAlmostEqual(res.confidence, 0.35)

    def test_nms_postprocessor(self):
        """Test Non-Maximum Suppression (NMS) removes overlapping duplicate boxes."""
        postprocessor = Postprocessor(self.config)

        # Setup heavily overlapping boxes of the same class (person=0.0)
        raw_output = np.zeros((1, 3, 6), dtype=np.float32)
        raw_output[0, 0] = [100, 100, 200, 200, 0.90, 0.0]   # Person, high confidence
        raw_output[0, 1] = [105, 105, 200, 200, 0.85, 0.0]   # Person, overlapping duplicate -> SUPPRESS
        raw_output[0, 2] = [300, 300, 400, 400, 0.70, 0.0]   # Person, separate -> KEEP

        results = postprocessor.postprocess(raw_output, [(640, 640)])[0]
        self.assertEqual(len(results), 2)
        
        # Verify coordinates of kept results
        self.assertAlmostEqual(results[0].box[0], 100.0)
        self.assertAlmostEqual(results[1].box[0], 300.0)

    def test_class_specific_nms(self):
        """Verify NMS does not suppress overlapping boxes of different classes."""
        postprocessor = Postprocessor(self.config)

        # Setup overlapping boxes of different classes (person=0.0 and car=2.0)
        raw_output = np.zeros((1, 2, 6), dtype=np.float32)
        raw_output[0, 0] = [100, 100, 200, 200, 0.90, 0.0]   # Person
        raw_output[0, 1] = [101, 101, 199, 199, 0.85, 2.0]   # Car -> KEEP (different class, no cross-class NMS)

        results = postprocessor.postprocess(raw_output, [(640, 640)])[0]
        self.assertEqual(len(results), 2)

    def test_letterbox_restoration(self):
        """Verify coordinate scaling back to original dimensions works properly."""
        postprocessor = Postprocessor(self.config)

        # Target size is 640x640. Original dims are 1280x720 (16:9).
        # Padding will apply top/bottom offsets.
        # Scale = min(640/1280, 640/720) = min(0.5, 0.888) = 0.5.
        # Resized width = 640, Resized height = 360.
        # Padding top = (640 - 360) // 2 = 140. Left = 0.
        original_dim = (1280, 720)
        
        # A detection box in letterboxed coordinates (e.g. left=100, top=140, right=200, bottom=320)
        raw_output = np.zeros((1, 1, 6), dtype=np.float32)
        raw_output[0, 0] = [100, 140, 200, 320, 0.95, 0.0]

        results = postprocessor.postprocess(raw_output, [original_dim])[0]
        self.assertEqual(len(results), 1)
        
        box = results[0].box
        # x coordinates unpadded: 100, 200. Scale=0.5 -> 200, 400.
        # y coordinates unpadded: (140-140)/0.5 = 0. (320-140)/0.5 = 360.
        self.assertAlmostEqual(box[0], 200.0)
        self.assertAlmostEqual(box[1], 0.0)
        self.assertAlmostEqual(box[2], 400.0)
        self.assertAlmostEqual(box[3], 360.0)

    @patch("detection.triton_client.grpcclient")
    def test_triton_fallback(self, mock_grpc):
        """Test Triton gRPC integration and automatic fallback if Triton server fails."""
        # Setup Triton config enabled
        triton_config = DetectionConfig(
            model_name="yolov10x_test",
            model_path=self.dummy_model_path,
            engine_path=self.dummy_engine_path,
            enable_triton=True,
            triton_server_url="localhost:8001",
        )

        # Mock grpc client to fail on server liveness check
        mock_client_instance = MagicMock()
        mock_grpc.InferenceServerClient.return_value = mock_client_instance
        mock_client_instance.is_server_live.side_effect = Exception("Connection refused")

        client = TritonInferenceClient(triton_config)
        self.assertFalse(client.connected)  # Connection fails

        # Try to run inference, verify it doesn't crash and returns output (via local fallback engine)
        batch = torch.randn(2, 3, 640, 640)
        results = client.infer(batch, [(640, 640), (640, 640)])
        self.assertEqual(len(results), 2)  # returns results for both batch elements

    @patch("detection.yolo_engine.HAS_NVML", True)
    @patch("detection.yolo_engine.pynvml")
    def test_gpu_utilization_nvml(self, mock_nvml):
        """Test NVML utilization metrics extraction."""
        mock_handle = MagicMock()
        mock_nvml.nvmlDeviceGetHandleByIndex.return_value = mock_handle
        
        mock_util = MagicMock()
        mock_util.gpu = 72
        mock_nvml.nvmlDeviceGetUtilizationRates.return_value = mock_util
        
        mock_mem = MagicMock()
        mock_mem.used = 8 * 1024 * 1024 * 1024
        mock_mem.total = 16 * 1024 * 1024 * 1024
        mock_nvml.nvmlDeviceGetMemoryInfo.return_value = mock_mem

        engine = YOLOTensorRTEngine(self.config)
        engine.nvml_initialized = True

        metrics = engine.get_gpu_utilization()
        self.assertEqual(metrics["gpu_utilization_percent"], 72.0)
        self.assertEqual(metrics["gpu_memory_used_mb"], 8192.0)
        self.assertEqual(metrics["gpu_memory_total_mb"], 16384.0)

    def test_int8_calibration_caching(self):
        """Verify the INT8 calibrator handles loading and writing calibration cache."""
        calib_data = [np.random.randint(0, 256, (3, 640, 640), dtype=np.uint8) for _ in range(4)]
        
        # Create a new calibrator instance
        calibrator = YOLOEntropyCalibrator(
            calibration_data=calib_data,
            cache_file=self.calibration_cache,
            batch_size=2,
            input_shape=(3, 640, 640)
        )

        # Initially, cache file should not exist, so read_calibration_cache returns None
        if os.path.exists(self.calibration_cache):
            os.remove(self.calibration_cache)
        self.assertIsNone(calibrator.read_calibration_cache())

        # Write dummy cache data
        dummy_cache = b"tensorrt-calibration-cache-data-blob"
        calibrator.write_calibration_cache(dummy_cache)
        
        # Now reading should return the dummy cache
        self.assertEqual(calibrator.read_calibration_cache(), dummy_cache)

    def test_benchmark_latency(self):
        """Execute warmup profiling and verify latency outputs are recorded."""
        engine = YOLOTensorRTEngine(self.config)
        engine.load_engine()

        stats = engine.warmup(num_runs=5)
        
        # Verify stats keys and data types
        self.assertIn("latency_p50_ms", stats)
        self.assertIn("latency_p95_ms", stats)
        self.assertIn("latency_p99_ms", stats)
        self.assertIn("throughput_fps", stats)
        
        self.assertGreater(stats["latency_p50_ms"], 0.0)
        self.assertGreater(stats["throughput_fps"], 0.0)

    def test_hot_swap_concurrency(self):
        """Verify thread-safe model registration and hot-swapping."""
        registry = ModelRegistry(self.config)

        # Create another dummy model ONNX file
        secondary_model_path = "models/test_secondary.onnx"
        secondary_engine_path = "models/test_secondary.engine"
        
        with open(secondary_model_path, "wb") as f:
            f.write(b"secondary-fake-onnx-model-data-surveillance")

        try:
            # Register secondary model
            registry.register_model(
                model_name="secondary",
                model_path=secondary_model_path,
                engine_path=secondary_engine_path,
            )

            # Define function to run inference continuously in background thread
            inference_error = False
            stop_event = threading.Event()

            def run_continuous_inference():
                nonlocal inference_error
                batch = torch.randn(4, 3, 640, 640)
                while not stop_event.is_set():
                    try:
                        out = registry.execute_inference(batch)
                        if out.shape != (4, 300, 6):
                            inference_error = True
                    except Exception as e:
                        print(f"Background thread inference exception: {e}")
                        inference_error = True
                    time.sleep(0.01)

            # Start background thread
            t = threading.Thread(target=run_continuous_inference)
            t.start()

            # Wait slightly, then hot-swap the model in the main thread
            time.sleep(0.1)
            swap_success = registry.hot_swap_model("secondary")
            self.assertTrue(swap_success)

            # Wait a bit longer, then stop background thread
            time.sleep(0.2)
            stop_event.set()
            t.join()

            # Check that background thread ran without errors
            self.assertFalse(inference_error)
            
            # Check that the active engine has been updated to the secondary one
            self.assertEqual(registry.get_active_engine().config.model_name, "secondary")

        finally:
            if os.path.exists(secondary_model_path):
                os.remove(secondary_model_path)
            if os.path.exists(secondary_engine_path):
                os.remove(secondary_engine_path)
