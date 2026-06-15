import base64
import os
import uuid
from typing import Any, Dict, List, Optional

import cv2
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.rbac.roles import RoleEnum
from app.core.security import get_current_user_payload, TokenPayload
from app.db.session import get_db
from app.models.schema_models import Camera, CameraAssignment, DetectedObject, VideoSegment
from app.services.search_cache import SearchCache
from app.api.v1.routers.chat import authenticate_ws
from search.search_coordinator import SearchCoordinator

logger = structlog.get_logger("api.search")

router = APIRouter(prefix="/search", tags=["Visual Search"])
detections_router = APIRouter(prefix="/detections", tags=["Detections"])

# Initialize Search Coordinator
search_coordinator = SearchCoordinator()


async def get_crop_auth(
    request: Request,
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> TokenPayload:
    """Authenticates the user via token query parameter, Authorization header, or API Key."""
    # 1. Try query param token
    if token:
        user = await authenticate_ws(token, db)
        if user:
            return user

    # 2. Try Authorization header or API Key
    auth_header = request.headers.get("Authorization")
    api_key = request.headers.get("X-API-Key")
    
    bearer_token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        bearer_token = auth_header[7:].strip()
        
    try:
        user = await get_current_user_payload(token=bearer_token, api_key=api_key, db=db)
        if user:
            return user
    except Exception:
        pass
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated"
    )


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
    
    1. Parses the query into structured parameters (SearchIntent) via rule-based parser.
    2. Enforces organization camera isolation (multi-tenancy and operator restrictions).
    3. Runs hybrid metadata and semantic fallback searches.
    4. Reranks and sorts results.
    """
    if not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty."
        )

    # Enforce organization camera isolation (multi-tenancy and operator restrictions)
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

    try:
        search_res = await search_coordinator.search(
            db_async_session=db,
            query_text=query,
            allowed_camera_ids=allowed_camera_ids or None,
            limit=limit,
            cursor=cursor
        )
    except Exception as e:
        logger.error("Failed to run visual search in coordinator", error=str(e))
        search_res = {
            "query": query,
            "intent": {},
            "results": [],
            "count": 0,
            "next_cursor": None,
            "search_source": "error",
            "latency_ms": 0.0
        }

    return search_res


@detections_router.get("/{id}/crop")
async def get_detection_crop(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_crop_auth)
):
    """Serves bounding box crop of a detection with Redis caching."""
    try:
        detection_uuid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid detection ID format.")

    # 1. Check Redis Cache
    cache = SearchCache()
    redis_client = await cache.get_client()
    cache_key = f"vq:crop:{id}"
    try:
        cached_b64 = await redis_client.get(cache_key)
        if cached_b64:
            jpeg_bytes = base64.b64decode(cached_b64.encode("utf-8"))
            return Response(content=jpeg_bytes, media_type="image/jpeg")
    except Exception as e:
        logger.warning("Failed to fetch crop from cache", error=str(e))

    # 2. Query DetectedObject
    stmt = select(DetectedObject).where(DetectedObject.id == detection_uuid)
    res = await db.execute(stmt)
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Detection not found.")

    # 3. Query VideoSegment
    segment_stmt = select(VideoSegment).where(VideoSegment.id == obj.segment_id)
    segment_res = await db.execute(segment_stmt)
    segment = segment_res.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="Video segment not found for detection.")

    # Fetch camera details to map to video file
    camera_stmt = select(Camera).where(Camera.id == segment.camera_id)
    camera_res = await db.execute(camera_stmt)
    camera = camera_res.scalar_one_or_none()
    
    # 4. Map camera to video file
    video_filename = "traffic-day-night.mp4"  # Default fallback
    if camera:
        cam_name = camera.name.lower()
        if "entrance" in cam_name or "lobby" in cam_name:
            video_filename = "video-lobby.mp4"
        elif "parking" in cam_name or "lot" in cam_name:
            video_filename = "video-parking.mp4"
        elif "traffic" in cam_name or "road" in cam_name or "intersection" in cam_name:
            video_filename = "traffic-ip.mp4"

    # Find the local path to video file
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
    video_path = os.path.join(project_root, "apps", "web", "public", "uploads", video_filename)

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"Source video file {video_filename} not found locally at {video_path}")

    # 5. Extract frame and crop bounding box
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(status_code=500, detail="Failed to open source video file.")

    if obj.frame_number >= 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, obj.frame_number)
    else:
        cap.set(cv2.CAP_PROP_POS_MSEC, obj.timestamp_ms)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise HTTPException(status_code=500, detail="Failed to read frame from video segment.")

    # Crop frame using normalized bounding box
    height, width, _ = frame.shape
    x1 = int(obj.bbox_x * width)
    y1 = int(obj.bbox_y * height)
    w = int(obj.bbox_w * width)
    h = int(obj.bbox_h * height)

    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(0, min(width, x1 + w))
    y2 = max(0, min(height, y1 + h))

    if x2 <= x1 or y2 <= y1:
        x1, y1, x2, y2 = 0, 0, width, height

    crop = frame[y1:y2, x1:x2]

    # Encode crop to JPEG
    ret, jpeg = cv2.imencode(".jpg", crop)
    if not ret:
        raise HTTPException(status_code=500, detail="Failed to encode image crop.")
    
    jpeg_bytes = jpeg.tobytes()

    # 6. Save to cache
    try:
        b64_str = base64.b64encode(jpeg_bytes).decode("utf-8")
        await redis_client.setex(cache_key, 3600, b64_str)
    except Exception as e:
        logger.warning("Failed to save crop to cache", error=str(e))

    return Response(content=jpeg_bytes, media_type="image/jpeg")
