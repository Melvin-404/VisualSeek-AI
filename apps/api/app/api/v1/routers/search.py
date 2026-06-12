import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.core.security import get_current_user_payload, TokenPayload
from app.core.rbac.roles import RoleEnum
from app.db.session import get_db
from app.models.schema_models import Camera, CameraAssignment
from app.services.nl_query.parser import NLUQueryParser
from app.services.vector_search import VectorSearchService
from app.services.query_parser import ParsedQuery

logger = structlog.get_logger("api.search")

router = APIRouter(prefix="/search", tags=["Visual Search"])

# Initialize NLU Parser and Vector Search Service
nlu_parser = NLUQueryParser()
vector_search_service = VectorSearchService()


@router.get("", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def search_visual_feed(
    query: str,
    collection: str = "frame_embeddings",
    limit: int = 10,
    cursor: Optional[str] = None,
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Exposes end-to-end visual semantic search capability.
    
    1. Parses the query into structured parameters (SearchIntent) via NLU pipeline.
    2. Enforces organization camera isolation (multi-tenancy and operator restrictions).
    3. Runs hybrid/semantic vector search in Milvus using cached connections.
    4. Returns parsed intent metadata and re-ranked vector search results.
    """
    if not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty."
        )

    # 1. Parse natural language query
    intent = await nlu_parser.parse(query)

    # 2. Determine allowed cameras based on user tenant and role (RBAC & Multi-tenancy)
    allowed_camera_ids: List[str] = []
    
    tenant_id = current_user.tenant_id
    if tenant_id:
        try:
            tenant_uuid = uuid.UUID(tenant_id)
            
            # Fetch cameras in this organization
            camera_stmt = select(Camera).where(Camera.org_id == tenant_uuid)
            camera_res = await db.execute(camera_stmt)
            cameras = camera_res.scalars().all()
            
            # Filter if role is OPERATOR (only allowed assigned cameras)
            if current_user.role == RoleEnum.OPERATOR:
                user_uuid = uuid.UUID(current_user.sub)
                assign_stmt = select(CameraAssignment.camera_id).where(
                    CameraAssignment.user_id == user_uuid
                )
                assign_res = await db.execute(assign_stmt)
                assigned_ids = {str(cid) for cid in assign_res.scalars().all()}
                
                allowed_camera_ids = [str(c.id) for c in cameras if str(c.id) in assigned_ids]
            else:
                allowed_camera_ids = [str(c.id) for c in cameras]
                
        except ValueError:
            logger.warning("Invalid tenant UUID format", tenant_id=tenant_id)
            allowed_camera_ids = []
    
    # Fallback to query-specified cameras if no organization cameras are found
    # (helps local testing and deployment offline modes without pre-seeded database records)
    if not allowed_camera_ids and current_user.role == "service":
        allowed_camera_ids = intent.camera_ids

    # 3. Map SearchIntent to ParsedQuery for VectorSearchService compatibility
    classes = [intent.object_class] if intent.object_class else []
    start_time = intent.time_range.get("start_ms") if intent.time_range else None
    end_time = intent.time_range.get("end_ms") if intent.time_range else None

    # Handle class name mapping for synonyms if needed (VectorSearchService expands this)
    parsed_query = ParsedQuery(
        raw_query=intent.raw_query,
        semantic_query=intent.rewritten_query or intent.raw_query,
        classes=classes,
        excluded_classes=intent.negations,
        start_time=start_time,
        end_time=end_time,
        camera_ids=intent.camera_ids,
        spatial_zone=intent.spatial_zone,
        expanded_synonyms=[]
    )

    # 4. Perform vector search in Milvus
    try:
        search_res = await vector_search_service.search(
            query_text=query,
            collection_name=collection,
            user_allowed_cameras=allowed_camera_ids,
            limit=limit,
            cursor=cursor,
            parsed_query_override=parsed_query
        )
    except Exception as e:
        logger.error("Failed to run vector search", error=str(e))
        search_res = {
            "results": [],
            "count": 0,
            "next_cursor": None,
            "cached": False,
            "latency_ms": 0.0
        }

    # 5. Build final response combining intent analysis details and matching objects
    return {
        "query": query,
        "intent": intent.to_dict(),
        "results": search_res.get("results", []),
        "count": search_res.get("count", 0),
        "next_cursor": search_res.get("next_cursor"),
        "cached": search_res.get("cached", False),
        "latency_ms": search_res.get("latency_ms", 0.0)
    }
