import os
import time
import base64
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pymilvus import connections, utility, Collection
import structlog

from app.core.config import settings
from app.services.search_cache import SearchCache
from embeddings.clip_encoder import CLIPEncoder
from embeddings.text_embedder import TextEmbedder
from search.query_parser import SearchIntent

logger = structlog.get_logger("search.semantic")


def get_collection_name(base_name: str) -> str:
    """Resolves Milvus collection name with environment prefix (e.g., dev_frame_embeddings)."""
    env = "dev"
    api_env = getattr(settings, "API_ENV", "development").lower()
    if "prod" in api_env:
        env = "prod"
    elif "test" in api_env:
        env = "test"
    elif "stage" in api_env or "staging" in api_env:
        env = "staging"
        
    if base_name.startswith(f"{env}_"):
        return base_name
    return f"{env}_{base_name}"


class SemanticSearch:
    """Performs semantic vector search matching text queries against CLIP frame/object embeddings in Milvus."""

    def __init__(self):
        # Initialize text embedder using ViT-B-32 to yield 512-dim vectors matching Milvus schemas
        encoder = CLIPEncoder(model_name="ViT-B-32")
        self.text_embedder = TextEmbedder(encoder)
        self.cache = SearchCache()
        self._ensure_connection()

    def _ensure_connection(self):
        """Ensures that a connection to the Milvus server is established."""
        try:
            if not connections.has_connection("default"):
                connections.connect(
                    alias="default",
                    host=settings.MILVUS_HOST,
                    port=settings.MILVUS_PORT,
                    timeout=1.0
                )
                logger.info("Milvus connection established in SemanticSearch", host=settings.MILVUS_HOST)
        except Exception as e:
            logger.error("Failed to connect to Milvus in SemanticSearch", error=str(e))

    def search(
        self,
        intent: SearchIntent,
        collection_name: str = "frame_embeddings",
        allowed_camera_ids: Optional[List[str]] = None,
        limit: int = 10,
        cursor: Optional[str] = None,
        bypass_cache: bool = False
    ) -> Dict[str, Any]:
        """Performs semantic query search over Milvus with Redis cache."""
        start_time_perf = time.perf_counter()
        self._ensure_connection()

        # 1. Resolve actual collection name/alias
        actual_col_name = get_collection_name(collection_name)

        # 2. Check search cache
        cache_key = self.cache.generate_key(
            query=intent.raw_query,
            filters={
                "collection": actual_col_name,
                "intent_type": intent.intent_type,
                "object_class": intent.object_class,
                "color": intent.color,
                "time_range_hours": intent.time_range_hours,
                "spatial_zone": intent.spatial_zone,
            },
            camera_ids=allowed_camera_ids or [],
            limit=limit,
            cursor=cursor
        )

        return self.search_sync(intent, collection_name, allowed_camera_ids, limit, cursor, bypass_cache)

    async def search_async(
        self,
        intent: SearchIntent,
        collection_name: str = "frame_embeddings",
        allowed_camera_ids: Optional[List[str]] = None,
        limit: int = 10,
        cursor: Optional[str] = None,
        bypass_cache: bool = False
    ) -> Dict[str, Any]:
        """Asynchronous execution of semantic search query."""
        start_time_perf = time.perf_counter()
        self._ensure_connection()

        actual_col_name = get_collection_name(collection_name)

        # 1. Check Cache
        cache_key = self.cache.generate_key(
            query=intent.raw_query,
            filters={
                "collection": actual_col_name,
                "intent_type": intent.intent_type,
                "object_class": intent.object_class,
                "color": intent.color,
                "time_range_hours": intent.time_range_hours,
                "spatial_zone": intent.spatial_zone,
            },
            camera_ids=allowed_camera_ids or [],
            limit=limit,
            cursor=cursor
        )

        if not bypass_cache:
            try:
                cached_results = await self.cache.get(cache_key)
                if cached_results:
                    logger.info("Semantic Search Cache Hit", query=intent.raw_query)
                    return {
                        "results": cached_results,
                        "count": len(cached_results),
                        "next_cursor": self._get_next_cursor(len(cached_results), limit, cursor),
                        "cached": True,
                        "latency_ms": (time.perf_counter() - start_time_perf) * 1000.0,
                    }
            except Exception as e:
                logger.warning("Cache retrieval failed in semantic search", error=str(e))

        # 2. Generate CLIP Text Embedding
        query_text = intent.semantic_query or intent.raw_query
        query_vector, _, _ = self.text_embedder.embed_text(query_text)

        # 3. Match dimension to 512
        query_vector = self._match_dimension(query_vector, target_dim=512)

        # 4. Formulate Milvus query boolean expression
        expr = self._build_milvus_expression(intent, allowed_camera_ids, actual_col_name)

        # 5. Decode cursor offset for pagination
        offset = self._decode_cursor(cursor)

        hits = []
        try:
            col = Collection(name=actual_col_name)
            col.load()

            search_params = {
                "metric_type": "COSINE",
                "params": {"ef": 64}
            }

            output_fields = ["id", "camera_id"]
            if "frame_embeddings" in actual_col_name:
                output_fields.extend(["timestamp_ms", "frame_number", "segment_id", "object_classes", "raw_labels"])
            elif "object_embeddings" in actual_col_name:
                output_fields.extend(["track_id", "class_label", "first_seen", "last_seen"])
            elif "event_embeddings" in actual_col_name:
                output_fields.extend(["event_id", "event_type", "severity", "start_time", "end_time", "metadata"])

            results = col.search(
                data=[query_vector.tolist()],
                anns_field="embedding",
                param=search_params,
                limit=limit,
                offset=offset,
                expr=expr,
                output_fields=output_fields,
            )

            if results and len(results) > 0:
                for hit in results[0]:
                    hit_dict = {}
                    for f in output_fields:
                        val = hit.entity.get(f)
                        if val.__class__.__name__ == "RepeatedScalarContainer":
                            val = list(val)
                        hit_dict[f] = val
                    hit_dict["score"] = hit.score
                    hit_dict["search_source"] = "semantic"
                    hits.append(hit_dict)
        except Exception as e:
            logger.error("Milvus search query failed in SemanticSearch", error=str(e))
            hits = []

        total_latency = (time.perf_counter() - start_time_perf) * 1000.0

        # Cache results if successful
        if hits and not bypass_cache:
            try:
                await self.cache.set(cache_key, hits, ttl=60)
            except Exception as e:
                logger.warning("Cache write failed in semantic search", error=str(e))

        return {
            "results": hits,
            "count": len(hits),
            "next_cursor": self._get_next_cursor(len(hits), limit, cursor),
            "cached": False,
            "latency_ms": total_latency,
        }

    def search_sync(
        self,
        intent: SearchIntent,
        collection_name: str = "frame_embeddings",
        allowed_camera_ids: Optional[List[str]] = None,
        limit: int = 10,
        cursor: Optional[str] = None,
        bypass_cache: bool = False
    ) -> Dict[str, Any]:
        """Synchronous wrapper for search query."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                self.search_async(intent, collection_name, allowed_camera_ids, limit, cursor, bypass_cache)
            )
        
        # If there is already a running loop, run in task or via executor
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(
                    self.search_async(intent, collection_name, allowed_camera_ids, limit, cursor, bypass_cache)
                )
            )
            return future.result()

    def _match_dimension(self, embedding: np.ndarray, target_dim: int) -> np.ndarray:
        """Projects embedding to target_dim if they mismatch."""
        curr_dim = embedding.shape[-1]
        if curr_dim == target_dim:
            return embedding
        rng = np.random.default_rng(42)
        proj = rng.standard_normal((curr_dim, target_dim)).astype(np.float32)
        q, _ = np.linalg.qr(proj)
        projected = np.dot(embedding, q)
        norm = np.linalg.norm(projected)
        return projected / max(norm, 1e-6)

    def _build_milvus_expression(
        self,
        intent: SearchIntent,
        allowed_camera_ids: Optional[List[str]],
        collection_name: str
    ) -> Optional[str]:
        """Builds boolean expression for metadata and class filtering."""
        clauses = []
        
        # Camera list restriction
        if allowed_camera_ids:
            cams_str = ", ".join([f"'{c}'" for c in allowed_camera_ids])
            clauses.append(f"camera_id in [{cams_str}]")
            
        # Time constraints - intent.time_range_hours is relative to now (in hours)
        if intent.time_range_hours is not None:
            now_ms = int(time.time() * 1000)
            start_time_ms = now_ms - int(intent.time_range_hours * 3600 * 1000)
            if "frame_embeddings" in collection_name:
                clauses.append(f"timestamp_ms >= {start_time_ms}")
            elif "object_embeddings" in collection_name:
                clauses.append(f"last_seen >= {start_time_ms}")
            else:
                clauses.append(f"end_time >= {start_time_ms}")

        # Classes and synonym expansions
        positive_classes = []
        if intent.object_class:
            positive_classes.append(intent.object_class)
            # Add basic synonyms/variants
            if intent.object_class == "car":
                positive_classes.extend(["vehicle", "automobile"])
            elif intent.object_class == "person":
                positive_classes.extend(["man", "woman", "pedestrian"])

        if positive_classes:
            class_clauses = []
            for cls in positive_classes:
                if "frame_embeddings" in collection_name:
                    class_clauses.append(f"array_contains(object_classes, '{cls}')")
                elif "object_embeddings" in collection_name:
                    class_clauses.append(f"class_label == '{cls}'")
                else:
                    class_clauses.append(f"event_type == '{cls}'")
            clauses.append(f"({' or '.join(class_clauses)})")

        return " and ".join(clauses) if clauses else None

    def _decode_cursor(self, cursor: Optional[str]) -> int:
        if not cursor:
            return 0
        try:
            decoded = base64.b64decode(cursor.encode("utf-8")).decode("utf-8")
            return int(decoded)
        except Exception:
            return 0

    def _get_next_cursor(self, results_len: int, limit: int, current_cursor: Optional[str]) -> Optional[str]:
        if results_len < limit:
            return None
        current_offset = self._decode_cursor(current_cursor)
        next_offset = current_offset + limit
        return base64.b64encode(str(next_offset).encode("utf-8")).decode("utf-8")
