"""Frame embedding generation pipeline with optional dimensionality reduction."""

import logging
import time
from typing import List, Tuple

import numpy as np

from embeddings.clip_encoder import CLIPEncoder

logger = logging.getLogger(__name__)


class FrameEmbedder:
    """Handles full-frame CLIP embedding extraction and optional 256-dim reduction."""

    def __init__(self, encoder: CLIPEncoder, enable_reduction: bool = False, reduction_dim: int = 256):
        """Initialize frame embedder."""
        self.encoder = encoder
        self.enable_reduction = enable_reduction
        self.reduction_dim = reduction_dim
        
        # Instantiate a stable, deterministic random projection matrix for dimension reduction
        # (Johnson-Lindenstrauss projection)
        if self.enable_reduction:
            rng = np.random.default_rng(42)  # Fixed seed for repeatable dimension mapping
            # Projection shape: (CLIP_dim, reduced_dim)
            proj = rng.standard_normal((self.encoder.embed_dim, self.reduction_dim)).astype(np.float32)
            # Orthogonalize projection matrix cols to preserve distances better
            q, _ = np.linalg.qr(proj)
            self.projection_matrix = q
            logger.info(
                "Dimensionality reduction enabled: projecting CLIP %d-dim to %d-dim.",
                self.encoder.embed_dim,
                self.reduction_dim,
            )

    def _project_dimension(self, embeddings: np.ndarray) -> np.ndarray:
        """Project embeddings down using the stable projection matrix and re-normalize."""
        projected = np.dot(embeddings, self.projection_matrix)
        # Re-normalize to unit length
        norms = np.linalg.norm(projected, axis=-1, keepdims=True)
        return projected / np.maximum(norms, 1e-6)

    def embed_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, str, float]:
        """Embed a single full video frame.

        Returns:
            Tuple of (embedding_vector, model_version_string, latency_ms).
        """
        embeddings, version, latency = self.embed_batch([frame])
        return embeddings[0], version, latency

    def embed_batch(self, frames: List[np.ndarray]) -> Tuple[np.ndarray, str, float]:
        """Embed a list/batch of full video frames.

        Returns:
            Tuple of (embeddings_ndarray, model_version_string, latency_ms).
        """
        start = time.perf_counter()
        
        # Encode frames
        embeddings, version, latency = self.encoder.encode_image(frames)
        
        # Apply projection if enabled
        if self.enable_reduction and len(embeddings) > 0:
            embeddings = self._project_dimension(embeddings)
            
        elapsed = (time.perf_counter() - start) * 1000.0
        return embeddings, version, elapsed
