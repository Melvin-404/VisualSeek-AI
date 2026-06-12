"""INT8 calibration helper for TensorRT engine optimization."""

import logging
import os
from typing import List, Optional, Union

import numpy as np

try:
    import tensorrt as trt
    HAS_TRT = True
except ImportError:
    trt = None
    HAS_TRT = False

try:
    import pycuda.driver as cuda
    import pycuda.autoinit  # noqa: F401
    HAS_PYCUDA = True
except ImportError:
    cuda = None
    HAS_PYCUDA = False

logger = logging.getLogger(__name__)

# Define base class based on TensorRT availability
BaseCalibrator = trt.IInt8EntropyCalibrator2 if HAS_TRT else object


class YOLOEntropyCalibrator(BaseCalibrator):
    """INT8 Calibrator implementing the IInt8EntropyCalibrator2 interface.

    Used to calibrate activations and weights to 8-bit precision.
    """

    def __init__(
        self,
        calibration_data: Union[List[np.ndarray], str],
        cache_file: str,
        batch_size: int = 8,
        input_shape: tuple = (3, 640, 640),
    ):
        """Initialize the calibrator.

        Args:
            calibration_data: A list of preprocessed frames as numpy arrays (shape [C, H, W]
                              or [H, W, C]), or a path to a directory of images.
            cache_file: Path to load/save the calibration cache.
            batch_size: Calibrator batch size.
            input_shape: Input tensor shape (C, H, W).
        """
        if HAS_TRT:
            super().__init__()

        self.cache_file = cache_file
        self.batch_size = batch_size
        self.input_shape = input_shape
        self.current_index = 0

        # Load calibration dataset
        self.data: List[np.ndarray] = []
        if isinstance(calibration_data, str):
            # Load images from directory if string path is provided
            if os.path.isdir(calibration_data):
                import cv2
                for fname in sorted(os.listdir(calibration_data)):
                    if fname.lower().endswith((".png", ".jpg", ".jpeg")):
                        img_path = os.path.join(calibration_data, fname)
                        img = cv2.imread(img_path)
                        if img is not None:
                            self.data.append(img)
            else:
                logger.warning(
                    "Calibration data path %s is not a directory. Calibrating with empty dataset.",
                    calibration_data,
                )
        elif isinstance(calibration_data, list):
            self.data = calibration_data
        else:
            logger.warning("Unsupported calibration data type. Calibrating with empty dataset.")

        # Ensure all data is preprocessed to (C, H, W) and normalized
        self.processed_data: List[np.ndarray] = []
        for img in self.data:
            proc_img = self._preprocess(img)
            self.processed_data.append(proc_img)

        # Allocate device memory if TensorRT and PyCUDA are available
        self.device_input = None
        if HAS_TRT and HAS_PYCUDA:
            try:
                # Size of one batch in bytes: batch_size * channels * height * width * sizeof(float32)
                item_size = np.dtype(np.float32).itemsize
                self.num_bytes = self.batch_size * np.prod(self.input_shape) * item_size
                self.device_input = cuda.mem_alloc(self.num_bytes)
            except Exception as e:
                logger.error("Failed to allocate CUDA memory for calibrator: %s", e)

    def _preprocess(self, img: np.ndarray) -> np.ndarray:
        """Preprocess frame to float32 (C, H, W) normalized to [0, 1]."""
        # Convert to float32
        proc = img.astype(np.float32)

        # If HWC, transpose to CHW
        if proc.ndim == 3:
            if proc.shape[2] == 3 or proc.shape[2] == 1:
                proc = proc.transpose(2, 0, 1)

        # Normalize to [0, 1] if not already
        if proc.max() > 1.0:
            proc /= 255.0

        # Resize/crop to input shape if shape differs
        c, h, w = self.input_shape
        if proc.shape != (c, h, w):
            # Fallback resizing using scipy/cv2 if dimensions mismatch
            import cv2
            # cv2 expects (H, W, C) for resize
            hwc = proc.transpose(1, 2, 0)
            resized = cv2.resize(hwc, (w, h), interpolation=cv2.INTER_LINEAR)
            if resized.ndim == 2:
                resized = np.expand_dims(resized, axis=-1)
            proc = resized.transpose(2, 0, 1)

        return proc

    def get_batch_size(self) -> int:
        """Get the batch size for calibration."""
        return self.batch_size

    def get_batch(self, names: List[str]) -> Optional[List[int]]:
        """Get the next batch of calibration data."""
        if not HAS_TRT or not HAS_PYCUDA or self.device_input is None:
            return None

        if self.current_index + self.batch_size > len(self.processed_data):
            # Out of calibration data
            return None

        # Build batch
        batch_slice = self.processed_data[self.current_index : self.current_index + self.batch_size]
        batch = np.ascontiguousarray(np.stack(batch_slice).astype(np.float32))

        # Copy data to GPU device memory
        cuda.memcpy_htod(self.device_input, batch)
        self.current_index += self.batch_size

        return [int(self.device_input)]

    def read_calibration_cache(self) -> Optional[bytes]:
        """Read the calibration cache if it exists."""
        if os.path.exists(self.cache_file):
            logger.info("Reading calibration cache from %s", self.cache_file)
            with open(self.cache_file, "rb") as f:
                return f.read()
        return None

    def write_calibration_cache(self, cache: bytes) -> None:
        """Write the calibration cache to disk."""
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.cache_file)), exist_ok=True)
        logger.info("Writing calibration cache to %s", self.cache_file)
        with open(self.cache_file, "wb") as f:
            f.write(cache)
