"""Text query embedding generation pipeline."""

import logging
from typing import List, Tuple

import numpy as np

from embeddings.clip_encoder import CLIPEncoder

logger = logging.getLogger(__name__)


class TextEmbedder:
    """Handles query-time text embedding generation using CLIP."""

    def __init__(self, encoder: CLIPEncoder):
        """Initialize text embedder."""
        self.encoder = encoder

    def embed_text(self, text: str) -> Tuple[np.ndarray, str, float]:
        """Embed a single query string.

        Returns:
            Tuple of (embedding_vector, model_version_string, latency_ms).
        """
        embeddings, version, latency = self.embed_queries([text])
        return embeddings[0], version, latency

    def embed_queries(self, queries: List[str]) -> Tuple[np.ndarray, str, float]:
        """Embed a list/batch of query strings.

        Returns:
            Tuple of (embeddings_ndarray, model_version_string, latency_ms).
        """
        return self.encoder.encode_text(queries)
