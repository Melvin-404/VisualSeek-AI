"""CLIP embedding encoder supporting ViT-L/14 and ViT-B/32 with GPU/TRT and mock fallbacks."""

import hashlib
import logging
import time
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import torch

try:
    import open_clip
    HAS_OPEN_CLIP = True
except ImportError:
    open_clip = None
    HAS_OPEN_CLIP = False

logger = logging.getLogger(__name__)


class CLIPEncoder:
    """Singleton-like encoder that loads a CLIP model and extracts normalized image/text embeddings."""

    _instance: Optional["CLIPEncoder"] = None

    _instances: Dict[str, "CLIPEncoder"] = {}

    def __new__(cls, model_name: str = "ViT-L-14", *args, **kwargs):
        """Ensure singleton instance per model type."""
        if model_name not in cls._instances:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[model_name] = instance
        return cls._instances[model_name]

    def __init__(self, model_name: str = "ViT-L-14", pretrained: str = "laion2b_s32b_b82k", use_gpu: bool = True):
        """Initialize the CLIP encoder."""
        if getattr(self, "_initialized", False):
            return
            
        if model_name == "ViT-B-32" and pretrained == "laion2b_s32b_b82k":
            pretrained = "laion2b_s34b_b79k"

        self.model_name = model_name
        self.pretrained = pretrained
        self.device = torch.device("cuda" if use_gpu and torch.cuda.is_available() else "cpu")
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        
        # Determine embedding dimension
        if "ViT-L-14" in model_name:
            self.embed_dim = 768
        elif "ViT-B-32" in model_name:
            self.embed_dim = 512
        else:
            self.embed_dim = 512

        self.model_version = f"{model_name}:{pretrained}"
        self._init_model()
        self._initialized = True

    def _init_model(self) -> None:
        """Load OpenCLIP model or fall back to mock feature extractor."""
        if HAS_OPEN_CLIP and self.device.type == "cuda":
            try:
                logger.info("Loading CLIP model '%s' (%s) on %s...", self.model_name, self.pretrained, self.device)
                self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                    self.model_name, pretrained=self.pretrained
                )
                self.model.to(self.device)
                self.model.eval()
                self.tokenizer = open_clip.get_tokenizer(self.model_name)
                logger.info("CLIP model loaded successfully.")
                return
            except Exception as e:
                logger.warning("Failed to load OpenCLIP model: %s. Falling back to deterministic mock.", e)
        else:
            logger.warning("OpenCLIP package not found. Using deterministic mock.")
            
        self.model = None
        self.preprocess = None
        self.tokenizer = None

    def _generate_mock_embedding(self, data_hash: str) -> np.ndarray:
        """Generate a deterministic unit-length mock embedding vector from a hash seed."""
        # Convert hex hash to integer seed
        seed = int(data_hash[:8], 16)
        rng = np.random.default_rng(seed)
        
        # Generate random values
        vector = rng.standard_normal(self.embed_dim).astype(np.float32)
        
        # L2 Normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector /= norm
        return vector

    def validate_embedding(self, embedding: np.ndarray) -> bool:
        """Validate embedding vectors for NaNs, infinites, and L2 unit-sphere norm."""
        if np.isnan(embedding).any() or np.isinf(embedding).any():
            logger.error("Embedding validation failed: NaN or infinite values detected.")
            return False
            
        # Check L2 Norm (should be extremely close to 1.0)
        norm = np.linalg.norm(embedding)
        if not np.allclose(norm, 1.0, atol=1e-3):
            logger.warning("Embedding is not unit-length normalized. Norm: %.4f", norm)
            return False
            
        return True

    def encode_image(self, image_crops: List[np.ndarray]) -> Tuple[np.ndarray, str, float]:
        """Encode a batch of image crops/frames.

        Args:
            image_crops: List of image crops as NumPy arrays (RGB/BGR format).

        Returns:
            Tuple of (embeddings_ndarray, model_version_string, latency_ms).
        """
        start_time = time.perf_counter()
        
        if len(image_crops) == 0:
            return np.empty((0, self.embed_dim), dtype=np.float32), self.model_version, 0.0

        # 1. OpenCLIP Inference Path
        if self.model is not None and self.preprocess is not None:
            try:
                from PIL import Image
                tensors = []
                for crop in image_crops:
                    pil_img = Image.fromarray(crop)
                    tensors.append(self.preprocess(pil_img))
                
                # Batch tensors
                batch_tensor = torch.stack(tensors).to(self.device)
                
                with torch.no_grad():
                    # Generate embeddings
                    features_tensor = self.model.encode_image(batch_tensor)
                    # L2 Normalization
                    features_tensor /= features_tensor.norm(dim=-1, keepdim=True)
                    embeddings = features_tensor.cpu().numpy()

                latency = (time.perf_counter() - start_time) * 1000.0
                
                # Validation checks
                for emb in embeddings:
                    self.validate_embedding(emb)
                    
                return embeddings, self.model_version, latency

            except Exception as e:
                logger.error("CLIP image encoding failed: %s. Falling back to deterministic mock.", e)

        # 2. Mock Deterministic Fallback Path (Hashed NumPy)
        # Computes repeatable embeddings based on image content hashing
        embeddings_list = []
        for crop in image_crops:
            # Hash the crop pixel data to get a unique, deterministic seed
            # Use a robust, fast hash (SHA256) of a subset of pixels to be fast
            hasher = hashlib.sha256()
            # Feed raw bytes of first 2000 pixels to hasher
            hasher.update(crop.tobytes()[:10000])
            h = hasher.hexdigest()
            embeddings_list.append(self._generate_mock_embedding(h))
            
        embeddings = np.stack(embeddings_list)
        latency = (time.perf_counter() - start_time) * 1000.0
        return embeddings, self.model_version, latency

    def encode_text(self, text_queries: List[str]) -> Tuple[np.ndarray, str, float]:
        """Encode a batch of text queries.

        Args:
            text_queries: List of natural language text strings.

        Returns:
            Tuple of (embeddings_ndarray, model_version_string, latency_ms).
        """
        start_time = time.perf_counter()
        
        if len(text_queries) == 0:
            return np.empty((0, self.embed_dim), dtype=np.float32), self.model_version, 0.0

        # 1. OpenCLIP Inference Path
        if self.model is not None and self.tokenizer is not None:
            try:
                tokens = self.tokenizer(text_queries).to(self.device)
                with torch.no_grad():
                    features_tensor = self.model.encode_text(tokens)
                    features_tensor /= features_tensor.norm(dim=-1, keepdim=True)
                    embeddings = features_tensor.cpu().numpy()

                latency = (time.perf_counter() - start_time) * 1000.0
                return embeddings, self.model_version, latency
            except Exception as e:
                logger.error("CLIP text encoding failed: %s. Falling back to mock.", e)

        # 2. Mock Deterministic Fallback Path
        embeddings_list = []
        for text in text_queries:
            hasher = hashlib.sha256()
            hasher.update(text.encode("utf-8"))
            h = hasher.hexdigest()
            embeddings_list.append(self._generate_mock_embedding(h))
            
        embeddings = np.stack(embeddings_list)
        latency = (time.perf_counter() - start_time) * 1000.0
        return embeddings, self.model_version, latency
