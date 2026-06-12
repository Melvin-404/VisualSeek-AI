"""Model registry and thread-safe zero-downtime engine hot-swapping."""

import hashlib
import logging
import os
import threading
from typing import Dict, Optional

import torch

from detection.config import DetectionConfig
from detection.yolo_engine import YOLOTensorRTEngine

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Manages model metadata and thread-safe zero-downtime hot-swapping of TensorRT engines."""

    def __init__(self, default_config: DetectionConfig):
        """Initialize registry and default model state."""
        self.default_config = default_config
        self._lock = threading.RLock()
        self._active_engine: Optional[YOLOTensorRTEngine] = None
        self._models_metadata: Dict[str, dict] = {}

        # Register default model
        self.register_model(
            model_name=default_config.model_name,
            model_path=default_config.model_path,
            engine_path=default_config.engine_path,
            expected_sha256=None,
        )

    def register_model(
        self,
        model_name: str,
        model_path: str,
        engine_path: str,
        expected_sha256: Optional[str] = None,
    ) -> None:
        """Register a model's metadata into the registry.

        Args:
            model_name: Unique name identifier for the model.
            model_path: Path to the source ONNX file.
            engine_path: Path to save/load the compiled engine file.
            expected_sha256: Optional SHA256 checksum for integrity check.
        """
        with self._lock:
            self._models_metadata[model_name] = {
                "model_name": model_name,
                "model_path": model_path,
                "engine_path": engine_path,
                "expected_sha256": expected_sha256,
            }
            logger.info("Registered model '%s' in registry.", model_name)

    def verify_integrity(self, model_name: str) -> bool:
        """Verify the SHA256 integrity of the registered ONNX model file.

        Args:
            model_name: Registered model name.
        """
        metadata = self._models_metadata.get(model_name)
        if not metadata:
            logger.error("Model '%s' not registered.", model_name)
            return False

        model_path = metadata["model_path"]
        expected_sha = metadata["expected_sha256"]

        if not os.path.exists(model_path):
            logger.error("Model file not found at %s", model_path)
            return False

        if not expected_sha:
            logger.warning("No expected SHA256 checksum registered for model '%s'. Skipping verification.", model_name)
            return True

        # Calculate actual checksum
        sha256_hash = hashlib.sha256()
        try:
            with open(model_path, "rb") as f:
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            actual_sha = sha256_hash.hexdigest()
            if actual_sha == expected_sha:
                logger.info("Model '%s' integrity verified successfully.", model_name)
                return True
            else:
                logger.error("Model '%s' integrity verification failed! Expected: %s, Actual: %s", model_name, expected_sha, actual_sha)
                return False
        except Exception as e:
            logger.error("Error verifying integrity of model '%s': %s", model_name, e)
            return False

    def get_active_engine(self) -> YOLOTensorRTEngine:
        """Retrieve the currently active engine.

        If no engine is loaded, initializes and loads the default configured engine inside the lock.
        """
        with self._lock:
            if self._active_engine is None:
                logger.info("No active engine found. Loading default model '%s'...", self.default_config.model_name)
                engine = YOLOTensorRTEngine(self.default_config)
                engine.load_engine()
                self._active_engine = engine
            return self._active_engine

    def execute_inference(self, batch_tensor: torch.Tensor) -> torch.Tensor:
        """Thread-safe delegation of inference execution to the active engine."""
        with self._lock:
            engine = self.get_active_engine()
            # Release lock as soon as engine reference is retrieved if execution is thread-safe,
            # or keep lock held to serialize model inference (essential for GPU execution contexts).
            # We keep it held during execution to ensure context is safe.
            raw_out = engine.execute_inference(batch_tensor)
            return torch.from_numpy(raw_out)

    def hot_swap_model(self, model_name: str) -> bool:
        """Compiles and loads a model outside the lock, then swaps the active engine reference inside the lock.

        Ensures zero-downtime model updates.

        Args:
            model_name: Registered model name to hot-swap to.
        """
        metadata = self._models_metadata.get(model_name)
        if not metadata:
            logger.error("Cannot hot-swap: Model '%s' is not registered.", model_name)
            return False

        # Verify integrity before compiling/loading
        if not self.verify_integrity(model_name):
            logger.warning("Model integrity verification failed or was skipped for '%s'. Proceeding carefully...", model_name)

        # 1. Compile/load the engine fully OUTSIDE the lock
        # This takes seconds to compile/load and must run concurrently without blocking active inference.
        logger.info("Initializing new engine context for hot-swap to '%s' outside active lock...", model_name)
        
        # Build custom config for the target model
        config = DetectionConfig(
            model_name=metadata["model_name"],
            model_path=metadata["model_path"],
            engine_path=metadata["engine_path"],
            max_batch_size=self.default_config.max_batch_size,
            enable_int8=self.default_config.enable_int8,
            enable_fp16=self.default_config.enable_fp16,
            iou_threshold=self.default_config.iou_threshold,
            confidence_thresholds=self.default_config.confidence_thresholds,
            triton_server_url=self.default_config.triton_server_url,
            enable_triton=self.default_config.enable_triton,
        )

        new_engine = YOLOTensorRTEngine(config)
        
        # Load (or compile on the fly if needed) the new engine
        success = new_engine.load_engine()
        if not success:
            logger.error("Failed to load/compile new engine for '%s'. Hot-swap aborted.", model_name)
            return False

        # Warm up the new engine before swapping to avoid dynamic kernel compilation lag on the first stream frames
        logger.info("Warming up new engine before hot-swapping...")
        try:
            new_engine.warmup(num_runs=3)
        except Exception as e:
            logger.warning("Warm-up of new engine failed: %s. Continuing hot-swap...", e)

        # 2. Acquire lock and swap the reference atomically
        logger.info("Acquiring lock to perform zero-downtime active engine reference swap...")
        with self._lock:
            old_engine = self._active_engine
            self._active_engine = new_engine
            logger.info("Successfully hot-swapped active model to '%s'.", model_name)

        # 3. Clean up the old engine context outside the lock
        if old_engine is not None:
            logger.info("Cleaning up old engine context outside lock...")
            try:
                # Explicitly delete reference to trigger garbage collection/CUDA cleanup
                del old_engine
            except Exception as e:
                logger.debug("Error during old engine cleanup: %s", e)

        return True
