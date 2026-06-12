"""CLIP feature extraction and embedding caching package."""

from embeddings.clip_encoder import CLIPEncoder
from embeddings.frame_embedder import FrameEmbedder
from embeddings.object_embedder import ObjectEmbedder
from embeddings.text_embedder import TextEmbedder
from embeddings.embedding_cache import EmbeddingCache

__all__ = [
    "CLIPEncoder",
    "FrameEmbedder",
    "ObjectEmbedder",
    "TextEmbedder",
    "EmbeddingCache",
]
