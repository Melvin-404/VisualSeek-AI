import json
import hashlib
from typing import List, Dict, Any, Optional
import structlog
import redis.asyncio as aioredis
from app.core.config import settings

logger = structlog.get_logger("search_cache")


class MockRedis:
    """Mock Redis client fallback when Redis server is unreachable."""
    def __init__(self):
        self.store = {}
        
    async def ping(self):
        return True
        
    async def get(self, key: str):
        val_info = self.store.get(key)
        if val_info:
            import time
            expire_at, val = val_info
            if time.time() < expire_at:
                return val
            else:
                del self.store[key]
        return None
        
    async def setex(self, key: str, ttl: int, value: str):
        import time
        self.store[key] = (time.time() + ttl, value)


class SearchCache:
    """Redis cache for identical semantic and hybrid queries (60s TTL)."""
    
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self.redis_url = settings.REDIS_URL
        
    async def get_client(self) -> Any:
        """Returns lazy-loaded async Redis client."""
        if self.redis_client is None:
            try:
                self.redis_client = aioredis.from_url(
                    self.redis_url, 
                    decode_responses=True,
                    socket_timeout=1.0
                )
                await self.redis_client.ping()
                logger.info("SearchCache successfully connected to Redis.")
            except Exception as e:
                logger.warning("SearchCache Redis connection failed. Falling back to in-memory dictionary.", error=str(e))
                # Create a simple mock dictionary client interface to prevent failures if Redis is down
                self.redis_client = MockRedis()
        return self.redis_client

    def generate_key(self, query: str, filters: Dict[str, Any], camera_ids: List[str], limit: int, cursor: Optional[str] = None) -> str:
        """Generates deterministic cache key using md5 hash of parameters."""
        normalized_filters = json.dumps(filters, sort_keys=True)
        normalized_cameras = ",".join(sorted(camera_ids))
        key_data = f"q:{query.strip().lower()}|f:{normalized_filters}|c:{normalized_cameras}|l:{limit}|cur:{cursor or ''}"
        hasher = hashlib.md5(key_data.encode("utf-8"))
        return f"vq:search:{hasher.hexdigest()}"

    async def get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        """Gets cached search results from Redis."""
        try:
            client = await self.get_client()
            data = await client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error("Failed to read from search cache", error=str(e))
        return None

    async def set(self, key: str, results: List[Dict[str, Any]], ttl: int = 60) -> None:
        """Saves search results in Redis with custom TTL."""
        try:
            client = await self.get_client()
            await client.setex(key, ttl, json.dumps(results))
        except Exception as e:
            logger.error("Failed to write to search cache", error=str(e))
