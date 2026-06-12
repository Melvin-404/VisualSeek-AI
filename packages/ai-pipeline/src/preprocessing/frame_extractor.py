"""GPU-accelerated frame extraction and motion filtering using SSIM."""

import logging
from typing import Generator, Optional, Tuple, Union

import av
import numpy as np
import torch
import torch.nn.functional as F
from scipy.ndimage import uniform_filter

logger = logging.getLogger(__name__)


def pytorch_ssim(img1: torch.Tensor, img2: torch.Tensor, window_size: int = 11) -> float:
    """Calculate Structural Similarity Index (SSIM) on the GPU using PyTorch.

    Args:
        img1: First frame tensor, either [C, H, W] or [1, C, H, W].
        img2: Second frame tensor.
        window_size: Size of the local filter window.

    Returns:
        SSIM value as a float between -1.0 and 1.0.
    """
    # Reshape tensors to [1, C, H, W] if necessary
    if img1.ndim == 2:
        img1 = img1.unsqueeze(0).unsqueeze(0)
        img2 = img2.unsqueeze(0).unsqueeze(0)
    elif img1.ndim == 3:
        img1 = img1.unsqueeze(0)
        img2 = img2.unsqueeze(0)

    # Convert to float and scale to [0, 1] if required
    img1 = img1.float()
    img2 = img2.float()
    if img1.max() > 1.0:
        img1 = img1 / 255.0
        img2 = img2 / 255.0

    # Ensure same device
    device = img1.device
    c1 = 0.01 ** 2
    c2 = 0.03 ** 2

    channels = img1.shape[1]
    # Create uniform window
    window = torch.ones((channels, 1, window_size, window_size), dtype=torch.float32, device=device) / (window_size ** 2)

    # Local means
    mu1 = F.conv2d(img1, window, padding=window_size // 2, groups=channels)
    mu2 = F.conv2d(img2, window, padding=window_size // 2, groups=channels)

    mu1_sq = mu1.pow(2)
    mu2_sq = mu2.pow(2)
    mu1_mu2 = mu1 * mu2

    # Local variances and covariance
    sigma1_sq = F.conv2d(img1 * img1, window, padding=window_size // 2, groups=channels) - mu1_sq
    sigma2_sq = F.conv2d(img2 * img2, window, padding=window_size // 2, groups=channels) - mu2_sq
    sigma12 = F.conv2d(img1 * img2, window, padding=window_size // 2, groups=channels) - mu1_mu2

    # SSIM index formula
    numerator = (2 * mu1_mu2 + c1) * (2 * sigma12 + c2)
    denominator = (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
    ssim_map = numerator / denominator

    return float(ssim_map.mean().item())


def numpy_ssim(img1: np.ndarray, img2: np.ndarray, window_size: int = 11) -> float:
    """Calculate Structural Similarity Index (SSIM) on the CPU using NumPy/SciPy.

    Args:
        img1: First frame array, either [H, W] or [H, W, C].
        img2: Second frame array.
        window_size: Size of the local filter window.

    Returns:
        SSIM value as a float.
    """
    # Convert multi-channel images to grayscale
    if img1.ndim == 3:
        img1 = 0.299 * img1[:, :, 0] + 0.587 * img1[:, :, 1] + 0.114 * img1[:, :, 2]
        img2 = 0.299 * img2[:, :, 0] + 0.587 * img2[:, :, 1] + 0.114 * img2[:, :, 2]

    img1 = img1.astype(np.float32)
    img2 = img2.astype(np.float32)
    if img1.max() > 1.0:
        img1 = img1 / 255.0
        img2 = img2 / 255.0

    c1 = 0.01 ** 2
    c2 = 0.03 ** 2

    # Local means
    mu1 = uniform_filter(img1, window_size)
    mu2 = uniform_filter(img2, window_size)

    mu1_sq = mu1 ** 2
    mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2

    # Local variances and covariance
    sigma1_sq = uniform_filter(img1 * img1, window_size) - mu1_sq
    sigma2_sq = uniform_filter(img2 * img2, window_size) - mu2_sq
    sigma12 = uniform_filter(img1 * img2, window_size) - mu1_mu2

    numerator = (2 * mu1_mu2 + c1) * (2 * sigma12 + c2)
    denominator = (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
    ssim_map = numerator / denominator

    return float(np.mean(ssim_map))


class GPUFrameExtractor:
    """Extracts frames using PyAV and performs motion-based keyframe selection.

    Uses GPU decoding where supported, else falls back to CPU.
    """

    def __init__(self, video_path: str, enable_gpu: bool = True):
        self.video_path = video_path
        self.enable_gpu = enable_gpu and torch.cuda.is_available()
        self.device = torch.device("cuda" if self.enable_gpu else "cpu")

        # Open container
        try:
            self.container = av.open(video_path)
            self.stream = self.container.streams.video[0]
        except Exception as e:
            logger.error("Failed to open video container %s: %s", video_path, e)
            raise

        # Attempt to initialize CUDA hardware acceleration inside PyAV context
        if self.enable_gpu:
            try:
                from av.codec.hwaccel import HWAccel
                cuda_hw = HWAccel(device_type="cuda")
                # PyAV allows passing hwaccel context dynamically or attaching to codec context
                # Attempt to register CUDA hwaccel if supported by PyAV compilation
                self.stream.codec_context.hwaccel = cuda_hw
                logger.info("PyAV CUDA hardware decode initialized for video: %s", video_path)
            except Exception as e:
                logger.debug("PyAV CUDA hwaccel not supported or failed to initialize: %s. Using CPU decode.", e)

    def calculate_ssim(
        self, frame1: Union[torch.Tensor, np.ndarray], frame2: Union[torch.Tensor, np.ndarray]
    ) -> float:
        """Calculates structural similarity index between two frames."""
        if isinstance(frame1, torch.Tensor) and isinstance(frame2, torch.Tensor):
            return pytorch_ssim(frame1, frame2)
        elif isinstance(frame1, np.ndarray) and isinstance(frame2, np.ndarray):
            return numpy_ssim(frame1, frame2)
        else:
            # Fallback/mix type conversions
            f1_np = frame1.cpu().numpy() if isinstance(frame1, torch.Tensor) else frame1
            f2_np = frame2.cpu().numpy() if isinstance(frame2, torch.Tensor) else frame2
            return numpy_ssim(f1_np, f2_np)

    def extract_frames(
        self, motion_threshold: float = 0.95
    ) -> Generator[Tuple[Union[torch.Tensor, np.ndarray], dict], None, None]:
        """Generator decoding video frames and filtering by motion threshold.

        Yields:
            Tuple of (frame_tensor_or_array, metadata_dict).
        """
        prev_frame_tensor = None
        frame_num = 0

        # Run decoder loop
        for frame in self.container.decode(self.stream):
            frame_num += 1
            timestamp_ms = int(frame.time * 1000)

            # Extract raw frame values as BGR24
            np_arr = frame.to_ndarray(format="bgr24")

            # Convert to appropriate device format
            if self.enable_gpu:
                # Upload frame directly to GPU memory
                curr_frame = torch.from_numpy(np_arr).to(self.device).permute(2, 0, 1)  # [C, H, W]
            else:
                curr_frame = np_arr

            # Perform motion filtering on consecutive frames
            motion_score = 0.0
            if prev_frame_tensor is not None:
                ssim_val = self.calculate_ssim(prev_frame_tensor, curr_frame)
                motion_score = 1.0 - ssim_val

                # Skip frame if there is not enough motion (i.e. highly similar / duplicate keyframe)
                if ssim_val >= motion_threshold:
                    continue

            # Update previous frame tracking
            prev_frame_tensor = curr_frame

            # Quality estimation (using variance of laplacian for blur, brightness mean)
            # Calculate simple scores on the current frame
            if self.enable_gpu:
                # PyTorch estimation
                gray = 0.299 * curr_frame[0] + 0.587 * curr_frame[1] + 0.114 * curr_frame[2]
                quality_score = float(gray.std().item())  # simple contrast standard deviation as quality proxy
            else:
                # NumPy estimation
                gray = 0.299 * curr_frame[:, :, 0] + 0.587 * curr_frame[:, :, 1] + 0.114 * curr_frame[:, :, 2]
                quality_score = float(gray.std())

            metadata = {
                "frame_number": frame_num,
                "timestamp_ms": timestamp_ms,
                "quality_score": quality_score,
                "motion_score": motion_score,
            }

            yield curr_frame, metadata

        self.container.close()
