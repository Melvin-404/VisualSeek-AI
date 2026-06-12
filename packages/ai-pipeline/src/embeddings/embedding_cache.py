"""Redis-based embedding cache with local in-memory dict fallbacks and TTL controls."""

import hashlib
import logging
from typing import Optional, Union

import numpy as np

try:
    import redis
    HAS_REDIS = True
except ImportError:
    redis = None
    HAS_REDIS = False

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """Caches generated float32 embedding vectors to avoid duplicate CLIP forward passes."""

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize the cache and set up fallbacks."""
        self.redis_client = None
        self.local_cache = {}  # In-memory fallback dictionary
        self.hits = 0
        self.misses = 0

        if redis_url and HAS_REDIS:
            try:
                self.redis_client = redis.from_url(redis_url)
                logger.info("Connected to Redis cache at %s", redis_url)
            except Exception as e:
                logger.warning("Failed to connect to Redis cache: %s. Using local memory cache.", e)

    def generate_key(self, image_data: np.ndarray, prefix: str = "frame") -> str:
        """Generate a unique SHA256 cache key from image pixel bytes."""
        hasher = hashlib.sha256()
        # Hash first 50KB to keep hashing extremely fast (<0.1ms)
        hasher.update(image_data.tobytes()[:50000])
        return f"clip_cache:{prefix}:{hasher.hexdigest()}"

    def get(self, key: str) -> Optional[np.ndarray]:
        """Retrieve an L2-normalized float32 embedding from cache."""
        # 1. Redis Cache
        if self.redis_client is not None:
            try:
                data = self.redis_client.get(key)
                if data is not None:
                    self.hits += 1
                    # Deserialize float32 numpy array from binary bytes
                    return np.frombuffer(data, dtype=np.float32).copy()
            except Exception as e:
                logger.error("Redis cache GET failed: %s", e)

        # 2. Local Fallback Cache
        if key in self.local_cache:
            self.hits += 1
            return self.local_cache[key].copy()

        self.misses += 1
        return None

    def set(self, key: str, embedding: np.ndarray, ttl: int = 86400) -> None:
        """Store an embedding in cache (binary serialization, default TTL = 24h)."""
        # Ensure array is contiguous and float32
        arr = np.ascontiguousarray(embedding.astype(np.float32))
        binary_data = arr.tobytes()

        # 1. Redis Cache
        if self.redis_client is not None:
            try:
                self.redis_client.setex(key, ttl, binary_data)
            except Exception as e:
                logger.error("Redis cache SET failed: %s", e)

        # 2. Local Fallback Cache
        self.local_cache[key] = arr.copy()

    @property
    def hit_rate(self) -> float:
        """Calculate the cache hit rate ratio."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return float(self.hits / total)

    def clear(self) -> None:
        """Clear the cache."""
        self.local_cache.clear()
        self.hits = 0
        self.misses = 0
        if self.redis_client is not None:
            try:
                self.redis_client.flushdb()
            except Exception:
                pass
