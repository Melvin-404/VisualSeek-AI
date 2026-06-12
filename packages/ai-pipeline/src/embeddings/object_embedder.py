"""Object crop embedding generation pipeline for detected bounding boxes."""

import logging
import time
from typing import List, Tuple

import cv2
import numpy as np

from embeddings.clip_encoder import CLIPEncoder

logger = logging.getLogger(__name__)


class ObjectEmbedder:
    """Crops detected bounding boxes from frames and generates independent object-level embeddings."""

    def __init__(self, encoder: CLIPEncoder, max_batch_size: int = 128):
        """Initialize object embedder."""
        self.encoder = encoder
        self.max_batch_size = max_batch_size

    def embed_objects(
        self, frame: np.ndarray, bboxes: List[Tuple[float, float, float, float]]
    ) -> Tuple[np.ndarray, str, float]:
        """Crop and embed multiple objects from a single frame.

        Args:
            frame: Raw frame image (RGB/BGR).
            bboxes: List of bounding boxes as [x1, y1, x2, y2].

        Returns:
            Tuple of (embeddings_ndarray, model_version_string, latency_ms).
        """
        start_time = time.perf_counter()
        
        if len(bboxes) == 0:
            return np.empty((0, self.encoder.embed_dim), dtype=np.float32), self.encoder.model_version, 0.0

        h, w = frame.shape[:2]
        crops = []

        for box in bboxes:
            x1, y1, x2, y2 = map(int, box)
            
            # Clip bbox coordinates to image dimensions
            x1 = max(0, min(x1, w - 1))
            y1 = max(0, min(y1, h - 1))
            x2 = max(0, min(x2, w - 1))
            y2 = max(0, min(y2, h - 1))

            if x2 > x1 and y2 > y1:
                crop = frame[y1:y2, x1:x2]
            else:
                # Fallback dummy patch for zero-area boxes
                crop = np.zeros((224, 224, 3), dtype=np.uint8)
            crops.append(crop)

        # Batch encoding (dynamic chunking up to max_batch_size)
        embeddings_list = []
        for i in range(0, len(crops), self.max_batch_size):
            chunk = crops[i : i + self.max_batch_size]
            chunk_embs, _, _ = self.encoder.encode_image(chunk)
            embeddings_list.append(chunk_embs)

        embeddings = np.concatenate(embeddings_list, axis=0)
        latency = (time.perf_counter() - start_time) * 1000.0
        
        return embeddings, self.encoder.model_version, latency
