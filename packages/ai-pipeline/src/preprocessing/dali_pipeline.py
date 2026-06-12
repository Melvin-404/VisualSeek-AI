"""NVIDIA DALI pipeline and PyTorch preprocessing fallback for video frames."""

import logging
from typing import List, Optional, Tuple, Union

import numpy as np
import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)

# Try importing NVIDIA DALI
try:
    from nvidia.dali import pipeline_def
    import nvidia.dali.fn as fn
    import nvidia.dali.types as types
    from nvidia.dali.pipeline import Pipeline
    DALI_AVAILABLE = True
except ImportError:
    DALI_AVAILABLE = False


def pytorch_letterbox(
    tensor: torch.Tensor, target_size: Tuple[int, int] = (640, 640), pad_value: float = 114 / 255.0
) -> torch.Tensor:
    """Preprocesses a single frame tensor to letterbox it while preserving aspect ratio.

    Args:
        tensor: Image tensor of shape [C, H, W] or [H, W, C] in range [0, 255].
        target_size: Target dimensions as (width, height).
        pad_value: Pixel value to fill the padded boundaries.

    Returns:
        Letterboxed image tensor of shape [C, target_height, target_width].
    """
    # Standardize shape to [C, H, W]
    if tensor.shape[2] == 3 or tensor.shape[2] == 1:
        tensor = tensor.permute(2, 0, 1)

    c, h, w = tensor.shape
    tw, th = target_size

    # Scale calculation
    scale = min(th / h, tw / w)
    new_h = int(round(h * scale))
    new_w = int(round(w * scale))

    # Resize
    float_tensor = tensor.unsqueeze(0).float()
    resized = F.interpolate(float_tensor, size=(new_h, new_w), mode="bilinear", align_corners=False).squeeze(0)

    # Scale values to [0, 1] if input was in [0, 255]
    if resized.max() > 1.0:
        resized = resized / 255.0

    # Create target canvas
    padded = torch.full((c, th, tw), pad_value, dtype=torch.float32, device=tensor.device)

    # Calculate padding offsets (center alignment)
    top = (th - new_h) // 2
    left = (tw - new_w) // 2

    # Place resized image in padded canvas
    padded[:, top : top + new_h, left : left + new_w] = resized
    return padded


def pytorch_normalize(
    tensor: torch.Tensor, mean: List[float] = [0.485, 0.456, 0.406], std: List[float] = [0.229, 0.224, 0.225]
) -> torch.Tensor:
    """Normalize a tensor image with mean and standard deviation."""
    device = tensor.device
    mean_t = torch.tensor(mean, dtype=torch.float32, device=device).view(-1, 1, 1)
    std_t = torch.tensor(std, dtype=torch.float32, device=device).view(-1, 1, 1)
    return (tensor - mean_t) / std_t


class PyTorchFallbackPipeline:
    """Fallback preprocessing pipeline using PyTorch CUDA/CPU tensor operations."""

    def __init__(self, target_size: Tuple[int, int] = (640, 640)):
        self.target_size = target_size

    def preprocess_batch(self, batch_tensors: List[torch.Tensor]) -> torch.Tensor:
        """Process list of image tensors.

        Args:
            batch_tensors: List of [C, H, W] or [H, W, C] tensors.

        Returns:
            A preprocessed batch tensor of shape [B, C, target_height, target_width].
        """
        processed_list = []
        for tensor in batch_tensors:
            letterboxed = pytorch_letterbox(tensor, self.target_size)
            normalized = pytorch_normalize(letterboxed)
            processed_list.append(normalized)

        return torch.stack(processed_list)


if DALI_AVAILABLE:

    class DALIVideoPipeline(Pipeline):
        """NVIDIA DALI pipeline for accelerated frame preprocessing directly on GPU."""

        def __init__(
            self,
            batch_size: int = 32,
            num_threads: int = 4,
            device_id: int = 0,
            target_size: Tuple[int, int] = (640, 640),
        ):
            super().__init__(batch_size, num_threads, device_id, seed=12)
            self.target_size = target_size
            self.device_id = device_id
            self._feed_data: List[np.ndarray] = []

        def set_feed_data(self, data_list: List[np.ndarray]) -> None:
            """Provide the batch data to feed into the external source."""
            self._feed_data = data_list

        def define_graph(self):
            # Define external source input feeding GPU decoded frames
            self.input_frames = fn.external_source(
                source=lambda: self._feed_data, device="gpu", name="frames", layout="HWC"
            )

            # 1. Resize/Letterbox
            # DALI resize keeps scale aspect ratio if using shorter/longer but pad fills background
            resized = fn.resize(
                self.input_frames,
                resize_x=self.target_size[0],
                resize_y=self.target_size[1],
                interp_type=types.INTERP_LINEAR,
            )

            # Convert to float and scale to [0, 1]
            float_frames = fn.cast(resized, dtype=types.FLOAT) / 255.0

            # 2. Normalize
            mean = fn.constant(value=[0.485, 0.456, 0.406], device="gpu")
            std = fn.constant(value=[0.229, 0.224, 0.225], device="gpu")
            normalized = (float_frames - mean) / std

            # 3. Transpose from HWC to CHW
            chw = fn.transpose(normalized, perm=[2, 0, 1])
            return chw

else:
    # Mock class in case DALI is not installed
    class DALIVideoPipeline:  # type: ignore[no-redef]
        def __init__(
            self,
            batch_size: int = 32,
            num_threads: int = 4,
            device_id: int = 0,
            target_size: Tuple[int, int] = (640, 640),
        ):
            self.batch_size = batch_size
            self.target_size = target_size
            logger.info("NVIDIA DALI not available. DALIVideoPipeline instantiated in fallback mode.")

        def set_feed_data(self, data_list: list) -> None:
            pass


class PreprocessingPipelineManager:
    """Manages preprocessing and determines whether to run DALI or PyTorch Fallback."""

    def __init__(self, target_size: Tuple[int, int] = (640, 640), enable_gpu: bool = True):
        self.target_size = target_size
        self.enable_gpu = enable_gpu and torch.cuda.is_available()
        self.device = torch.device("cuda" if self.enable_gpu else "cpu")

        # Initialize fallback pipeline
        self.fallback_pipeline = PyTorchFallbackPipeline(target_size)

        # Initialize DALI if available and GPU mode enabled
        self.dali_pipeline: Optional[DALIVideoPipeline] = None
        if DALI_AVAILABLE and self.enable_gpu:
            try:
                self.dali_pipeline = DALIVideoPipeline(
                    batch_size=32, num_threads=4, device_id=0, target_size=target_size
                )
                self.dali_pipeline.build()
                logger.info("NVIDIA DALI pipeline successfully initialized.")
            except Exception as e:
                logger.warning("Failed to build NVIDIA DALI pipeline: %s. Using PyTorch fallback.", e)
                self.dali_pipeline = None

    def preprocess(self, frames: List[Union[torch.Tensor, np.ndarray]]) -> torch.Tensor:
        """Preprocesses a list of frames.

        Automatically uses DALI if built, else uses the PyTorch fallback.

        Args:
            frames: List of frames to preprocess.

        Returns:
            Preprocessed batch tensor of shape [B, C, H, W].
        """
        # Convert all frames to PyTorch tensors on target device
        tensor_list = []
        for f in frames:
            if isinstance(f, torch.Tensor):
                tensor_list.append(f.to(self.device))
            else:
                tensor_list.append(torch.from_numpy(f).to(self.device))

        # Check if DALI can be used (requires GPU and frames as NumPy lists)
        if self.dali_pipeline is not None and self.enable_gpu:
            try:
                # Convert PyTorch tensors to NumPy arrays for DALI feed_input
                # Note: DALI feed_input supports cupy/pytorch gpu pointers directly in newer versions,
                # but numpy list is universally supported via external_source
                np_frames = [f.cpu().numpy() if isinstance(f, torch.Tensor) else f for f in frames]
                self.dali_pipeline.set_feed_data(np_frames)
                outputs = self.dali_pipeline.run()
                # Retrieve first output (CHW batch)
                dali_tensor = outputs[0].as_tensor()
                # Wrap as PyTorch CUDA tensor
                from torch.utils.dlpack import from_dlpack
                dlpack = dali_tensor._to_dlpack()
                return from_dlpack(dlpack)
            except Exception as e:
                logger.warning("DALI execution failed: %s. Falling back to PyTorch preprocessing.", e)

        # Fallback processing
        return self.fallback_pipeline.preprocess_batch(tensor_list)
