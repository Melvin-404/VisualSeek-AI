"""Frame quality assessment for video ingestion.

Provides blur detection (Laplacian variance), darkness detection
(mean luminance), and frozen frame detection (structural similarity)
to filter low-quality frames before storage.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from ingestion.config import IngestionConfig

logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    """Result of frame quality assessment."""

    is_acceptable: bool
    blur_score: float  # Laplacian variance (higher = sharper)
    brightness_score: float  # Mean luminance (0-255)
    frozen_score: float  # SSIM with previous frame (0-1, higher = more similar)
    checked_at: float  # Unix timestamp


class FrameQualityChecker:
    """Assesses video frame quality using multiple metrics.

    Runs blur, darkness, and frozen-frame checks. GPU-accelerated
    when CUDA is available, otherwise falls back to CPU.

    Args:
        config: Ingestion configuration with quality thresholds.
    """

    def __init__(self, config: Optional[IngestionConfig] = None) -> None:
        self.config = config or IngestionConfig()
        self._prev_gray: Optional[np.ndarray] = None
        self._has_cuda = self._check_cuda()

    @staticmethod
    def _check_cuda() -> bool:
        """Check if OpenCV CUDA support is available."""
        try:
            return cv2.cuda.getCudaEnabledDeviceCount() > 0
        except AttributeError:
            return False

    def check(
        self, frame: np.ndarray, prev_frame: Optional[np.ndarray] = None
    ) -> QualityReport:
        """Run all quality checks on a frame.

        Args:
            frame: BGR image array.
            prev_frame: Previous frame for frozen detection (optional).
                If None, uses internally cached previous frame.

        Returns:
            QualityReport with scores and pass/fail verdict.
        """
        is_blur, blur_score = self.is_blurry(frame)
        is_dark, brightness_score = self.is_dark(frame)

        # Use provided prev_frame or internal cache
        reference = prev_frame if prev_frame is not None else self._prev_gray
        is_frozen, frozen_score = self.is_frozen(frame, reference)

        # Cache current frame as grayscale for next check
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self._prev_gray = gray

        # Frame is unacceptable if blurry AND dark, or frozen
        is_acceptable = not (is_blur and is_dark) and not is_frozen

        return QualityReport(
            is_acceptable=is_acceptable,
            blur_score=blur_score,
            brightness_score=brightness_score,
            frozen_score=frozen_score,
            checked_at=time.time(),
        )

    def is_blurry(self, frame: np.ndarray) -> tuple[bool, float]:
        """Detect blur using Laplacian variance method.

        Lower variance indicates a blurrier image.

        Args:
            frame: BGR image array.

        Returns:
            Tuple of (is_blurry, laplacian_variance).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self._has_cuda:
            try:
                gpu_gray = cv2.cuda_GpuMat()
                gpu_gray.upload(gray)
                gpu_lap = cv2.cuda.createLaplacianFilter(
                    cv2.CV_8UC1, cv2.CV_64F
                )
                gpu_result = gpu_lap.apply(gpu_gray)
                laplacian = gpu_result.download()
            except cv2.error:
                # Fallback to CPU
                laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        else:
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)

        variance = float(laplacian.var())
        is_blur = variance < self.config.quality.blur_threshold

        return is_blur, variance

    def is_dark(self, frame: np.ndarray) -> tuple[bool, float]:
        """Detect darkness using mean luminance.

        Args:
            frame: BGR image array.

        Returns:
            Tuple of (is_dark, mean_luminance).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_luminance = float(np.mean(gray))
        is_dark = mean_luminance < self.config.quality.darkness_threshold

        return is_dark, mean_luminance

    def is_frozen(
        self, frame: np.ndarray, prev_frame: Optional[np.ndarray] = None
    ) -> tuple[bool, float]:
        """Detect frozen/stuck frames using structural similarity.

        Compares current frame to previous using normalized correlation.
        High similarity (>0.98) suggests the camera feed is frozen.

        Args:
            frame: BGR image array.
            prev_frame: Previous grayscale frame for comparison.

        Returns:
            Tuple of (is_frozen, similarity_score).
        """
        if prev_frame is None:
            return False, 0.0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Ensure same dimensions
        if gray.shape != prev_frame.shape:
            return False, 0.0

        # Normalized cross-correlation as a fast SSIM approximation
        result = cv2.matchTemplate(gray, prev_frame, cv2.TM_CCORR_NORMED)
        similarity = float(result[0][0]) if result.size > 0 else 0.0
        is_frozen = similarity > self.config.quality.frozen_threshold

        return is_frozen, similarity

    def reset(self) -> None:
        """Reset internal state (previous frame cache)."""
        self._prev_gray = None
