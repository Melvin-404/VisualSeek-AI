import datetime
import time
import uuid
from typing import List, Dict, Any, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from search.query_parser import QueryParser, SearchIntent
from search.metadata_search import MetadataSearch
from search.semantic_search import SemanticSearch
from search.reid_search import ReIDSearch
from search.reranker import SearchReranker
from search.temporal_search import TemporalSearch

logger = structlog.get_logger("search.coordinator")


class SearchCoordinator:
    """Orchestrates multi-stage query parsing, structured metadata searches, semantic fallbacks, ReID tracing, and result rerankers."""

    def __init__(self):
        self.query_parser = QueryParser()
        self.metadata_search = MetadataSearch()
        self.semantic_search = SemanticSearch()
        self.reid_search = ReIDSearch()
        self.reranker = SearchReranker()
        self.temporal_search = TemporalSearch()

    async def search(
        self,
        db_async_session: AsyncSession,
        query_text: str,
        allowed_camera_ids: Optional[List[str]] = None,
        limit: int = 10,
        cursor: Optional[str] = None,
        bypass_cache: bool = False
    ) -> Dict[str, Any]:
        """Runs the multi-stage visual search pipeline."""
        start_time = time.perf_counter()

        # 1. Parse query intent
        intent = self.query_parser.parse(query_text)
        logger.info("Parsed query intent", query=query_text, intent=intent)

        # Helper function to run database operations on the synchronous Session wrapped by AsyncSession
        def sync_search_pipeline(session):
            hits = []
            source = "metadata"

            # Check if intent is Cross-Camera tracking
            if intent.intent_type == "cross_camera_track":
                logger.info("Executing Cross-Camera ReID search")
                from app.models.schema_models import IdentityGallery
                gallery_query = session.query(IdentityGallery)
                if intent.object_class:
                    gallery_query = gallery_query.filter(IdentityGallery.object_type == intent.object_class)
                
                recent_gallery = gallery_query.order_by(IdentityGallery.created_at.desc()).first()
                if recent_gallery:
                    logger.info("Found gallery profile for tracking", gallery_id=str(recent_gallery.id))
                    hits = self.reid_search.search_by_gallery_id(
                        session=session,
                        gallery_id=recent_gallery.id,
                        allowed_camera_ids=allowed_camera_ids,
                        limit=limit
                    )
                    source = "reid_trajectory"
                else:
                    hits = []
            else:
                # Standard Search: Execute Metadata Search
                logger.info("Executing structured metadata search")
                hits = self.metadata_search.search(
                    session=session,
                    intent=intent,
                    allowed_camera_ids=allowed_camera_ids,
                    limit=limit
                )
            
            return hits, source

        # Execute PostgreSQL queries inside run_sync
        hits, source = await db_async_session.run_sync(sync_search_pipeline)

        # 2. Semantic Fallback: if we have fewer hits than requested limit
        if len(hits) < limit and intent.intent_type != "cross_camera_track":
            logger.info("Metadata search yielded sparse results, falling back to CLIP semantic search", current_count=len(hits))
            semantic_limit = limit - len(hits)
            try:
                semantic_res = await self.semantic_search.search_async(
                    intent=intent,
                    collection_name="frame_embeddings",
                    allowed_camera_ids=allowed_camera_ids,
                    limit=semantic_limit * 2,
                    bypass_cache=bypass_cache
                )
                semantic_hits = semantic_res.get("results", [])
                
                # Merge semantic hits avoiding duplicates
                seen_ids = {h["id"] for h in hits}
                merged_count = 0
                for sh in semantic_hits:
                    sh_id = sh.get("id")
                    if sh_id not in seen_ids:
                        sh["search_source"] = "semantic"
                        hits.append(sh)
                        seen_ids.add(sh_id)
                        merged_count += 1
                logger.info("Merged semantic fallback hits", added=merged_count)
                if merged_count > 0:
                    source = "hybrid"
            except Exception as e:
                logger.error("Semantic fallback failed", error=str(e))

        # 3. Map Camera ID for display (if missing)
        if hits:
            def sync_camera_mapper(session):
                segment_camera_map = {}
                segment_ids = [uuid.UUID(h["segment_id"]) for h in hits if h.get("segment_id") and not h.get("camera_id")]
                
                if segment_ids:
                    from app.models.schema_models import VideoSegment
                    segments = session.query(VideoSegment.id, VideoSegment.camera_id).filter(VideoSegment.id.in_(segment_ids)).all()
                    segment_camera_map = {str(s_id): str(cam_id) for s_id, cam_id in segments}
                return segment_camera_map
            
            segment_camera_map = await db_async_session.run_sync(sync_camera_mapper)
            
            for h in hits:
                if not h.get("camera_id") and h.get("segment_id"):
                    h["camera_id"] = segment_camera_map.get(h["segment_id"])

        # 4. Apply Reranking combining semantic score, metadata similarity, and temporal decay
        logger.info("Applying reranker on hits", count=len(hits))
        final_hits = self.reranker.rerank(intent=intent, hits=hits)

        # 5. Truncate to limit
        final_hits = final_hits[:limit]

        # 6. Formulate next cursor
        next_cursor = self.semantic_search._get_next_cursor(len(final_hits), limit, cursor)

        latency = (time.perf_counter() - start_time) * 1000.0
        return {
            "query": query_text,
            "intent": {
                "intent_type": intent.intent_type,
                "object_class": intent.object_class,
                "color": intent.color,
                "vehicle_style": intent.vehicle_style,
                "attributes": intent.attributes,
                "gender": intent.gender,
                "spatial_zone": intent.spatial_zone,
                "time_range_hours": intent.time_range_hours,
            },
            "results": final_hits,
            "count": len(final_hits),
            "next_cursor": next_cursor,
            "search_source": source,
            "latency_ms": latency
        }
