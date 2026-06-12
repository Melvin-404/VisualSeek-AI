"""Perceptual hashing (pHash) and frame deduplication on GPU/CPU."""

import collections
import logging
from typing import Optional, Union

import numpy as np
import PIL.Image
import torch
import torch.nn.functional as F

# Try importing imagehash
try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

logger = logging.getLogger(__name__)


def get_dct_matrix(n: int = 32, device: Optional[torch.device] = None) -> torch.Tensor:
    """Precompute the 1D Discrete Cosine Transform matrix of size n x n."""
    C = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(n):
            if i == 0:
                C[i, j] = 1.0 / np.sqrt(n)
            else:
                C[i, j] = np.sqrt(2.0 / n) * np.cos(np.pi * (2 * j + 1) * i / (2.0 * n))
    return torch.from_numpy(C).to(device)


class FrameDeduplicator:
    """Computes perceptual hashes of frames and filters duplicates using a sliding window.

    GPU-accelerated when CUDA is available, else falls back to CPU.
    """

    def __init__(self, phash_threshold: int = 4, window_size: int = 300, enable_gpu: bool = True):
        self.phash_threshold = phash_threshold
        self.window_size = window_size
        self.enable_gpu = enable_gpu and torch.cuda.is_available()
        self.device = torch.device("cuda" if self.enable_gpu else "cpu")

        # Sliding window of hashes
        self.hash_window = collections.deque(maxlen=window_size)

        # Precompute DCT matrix for GPU pHash
        self.dct_matrix = get_dct_matrix(32, self.device)

    def compute_phash_gpu(self, frame_tensor: torch.Tensor) -> str:
        """GPU-accelerated DCT-based perceptual hash computation using PyTorch.

        Args:
            frame_tensor: Image tensor of shape [C, H, W] or [H, W, C].

        Returns:
            A 64-bit hex hash string.
        """
        # Convert to [C, H, W] if necessary
        if frame_tensor.shape[2] == 3 or frame_tensor.shape[2] == 1:
            frame_tensor = frame_tensor.permute(2, 0, 1)

        # 1. Grayscale conversion
        if frame_tensor.shape[0] == 3:
            gray = 0.299 * frame_tensor[0] + 0.587 * frame_tensor[1] + 0.114 * frame_tensor[2]
        else:
            gray = frame_tensor[0]

        # 2. Resize to 32x32
        gray_batch = gray.unsqueeze(0).unsqueeze(0).float()
        resized = F.interpolate(gray_batch, size=(32, 32), mode="bilinear", align_corners=False).squeeze()

        # 3. 2D DCT: Y = C * X * C^T
        dct = torch.mm(torch.mm(self.dct_matrix, resized), self.dct_matrix.t())

        # 4. Extract top-left 8x8 coefficients
        top_left = dct[0:8, 0:8]

        # 5. Compute mean excluding the DC coefficient (0,0)
        flat = top_left.flatten()
        mean_val = flat[1:].mean()

        # 6. Generate 64-bit binary mask
        mask = top_left > mean_val

        # 7. Convert mask to 64-bit integer and then hex string
        flat_mask = mask.flatten()
        hash_int = 0
        for bit in flat_mask:
            hash_int = (hash_int << 1) | int(bit.item())

        return f"{hash_int:016x}"

    def compute_phash_cpu(self, frame_array: np.ndarray) -> str:
        """CPU perceptual hash computation using PIL and imagehash."""
        if not IMAGEHASH_AVAILABLE:
            # Simple fallback hash if imagehash is not available
            gray = 0.299 * frame_array[:, :, 0] + 0.587 * frame_array[:, :, 1] + 0.114 * frame_array[:, :, 2]
            resized = gray[::gray.shape[0]//8, ::gray.shape[1]//8][:8, :8]
            mean = resized.mean()
            mask = resized > mean
            hash_int = 0
            for row in mask:
                for bit in row:
                    hash_int = (hash_int << 1) | int(bit)
            return f"{hash_int:016x}"

        # standard imagehash
        pil_img = PIL.Image.fromarray(frame_array)
        val = imagehash.phash(pil_img)
        return str(val)

    def compute_phash(self, frame: Union[torch.Tensor, np.ndarray]) -> str:
        """Compute perceptual hash for a frame array or tensor."""
        if self.enable_gpu and isinstance(frame, torch.Tensor):
            return self.compute_phash_gpu(frame)
        else:
            # Convert to NumPy for CPU hash
            np_frame = frame.cpu().numpy() if isinstance(frame, torch.Tensor) else frame
            return self.compute_phash_cpu(np_frame)

    @staticmethod
    def hamming_distance(hash1_str: str, hash2_str: str) -> int:
        """Calculate Hamming distance between two hex hash strings."""
        val1 = int(hash1_str, 16)
        val2 = int(hash2_str, 16)
        return bin(val1 ^ val2).count("1")

    def is_duplicate(self, frame: Union[torch.Tensor, np.ndarray]) -> bool:
        """Check if frame is a duplicate by comparing its hash against the sliding window.

        Args:
            frame: Frame array or tensor.

        Returns:
            True if duplicate, False otherwise.
        """
        curr_hash = self.compute_phash(frame)

        for h in self.hash_window:
            dist = self.hamming_distance(curr_hash, h)
            if dist <= self.phash_threshold:
                # Duplicate found
                return True

        # Unique frame, record hash in window
        self.hash_window.append(curr_hash)
        return False

    def clear(self) -> None:
        """Clear the sliding window."""
        self.hash_window.clear()
