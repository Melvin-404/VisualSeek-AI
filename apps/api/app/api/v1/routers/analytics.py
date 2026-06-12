import uuid
import json
import os
import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user_payload, TokenPayload
from app.db.session import get_db
from app.services.analytics_service import AnalyticsService

logger = structlog.get_logger("api.routers.analytics")

router = APIRouter(prefix="/analytics", tags=["Executive Analytics"])


def get_tenant_uuid(current_user: TokenPayload) -> uuid.UUID:
    """Helper to parse and validate tenant ID from user token."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        # Fallback to default test tenant UUID
        return uuid.UUID("22222222-2222-2222-2222-222222222222")
    try:
        return uuid.UUID(tenant_id)
    except ValueError:
        logger.error("Invalid tenant UUID format in token", tenant_id=tenant_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization/tenant ID."
        )


@router.get("/kpis", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def get_overview_kpis(
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Retrieves real-time active cameras, events per hour, queries per min, and GPU load."""
    org_id = get_tenant_uuid(current_user)
    try:
        return await AnalyticsService.get_realtime_kpis(db, org_id)
    except Exception as e:
        logger.error("Failed to fetch KPIs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch KPIs: {str(e)}"
        )


@router.get("/heatmap", response_model=List[Dict[str, Any]], status_code=status.HTTP_200_OK)
async def get_traffic_heatmap(
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Returns zone foot traffic density aggregated per hour."""
    org_id = get_tenant_uuid(current_user)
    try:
        return await AnalyticsService.get_traffic_heatmap(db, org_id)
    except Exception as e:
        logger.error("Failed to fetch traffic heatmap", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch traffic heatmap: {str(e)}"
        )


@router.get("/trends", response_model=List[Dict[str, Any]], status_code=status.HTTP_200_OK)
async def get_historical_trends(
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Fetches daily object count trends (people and vehicles) over the last 90 days."""
    org_id = get_tenant_uuid(current_user)
    try:
        return await AnalyticsService.get_object_trends(db, org_id)
    except Exception as e:
        logger.error("Failed to fetch historical trends", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch object trends: {str(e)}"
        )


@router.get("/event-distribution", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def get_event_distribution(
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Returns classification details, severity, and peak hours for events."""
    org_id = get_tenant_uuid(current_user)
    try:
        return await AnalyticsService.get_event_analytics(db, org_id)
    except Exception as e:
        logger.error("Failed to fetch event distribution", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch event analytics: {str(e)}"
        )


@router.get("/camera-health", response_model=List[Dict[str, Any]], status_code=status.HTTP_200_OK)
async def get_camera_health_matrix(
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Provides uptime %, frame drop rates, and latency per camera."""
    org_id = get_tenant_uuid(current_user)
    try:
        return await AnalyticsService.get_camera_health(db, org_id)
    except Exception as e:
        logger.error("Failed to fetch camera health", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch camera health: {str(e)}"
        )


@router.get("/search-stats", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def get_search_analytics(
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Retrieves top search terms, average search latencies, and zero-result rates."""
    org_id = get_tenant_uuid(current_user)
    try:
        return await AnalyticsService.get_search_analytics(db, org_id)
    except Exception as e:
        logger.error("Failed to fetch search stats", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch search stats: {str(e)}"
        )


@router.get("/gpu", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def get_gpu_analytics(
    current_user: TokenPayload = Depends(get_current_user_payload)
) -> Dict[str, Any]:
    """Returns CUDA cores, temperature, memory allocation, and power draw."""
    try:
        return await AnalyticsService.get_gpu_utilization()
    except Exception as e:
        logger.error("Failed to fetch GPU analytics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch GPU utilization: {str(e)}"
        )


@router.get("/alert-fatigue", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def get_alert_fatigue_stats(
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Analyzes true vs false positive alert ratios to optimize threshold configs."""
    org_id = get_tenant_uuid(current_user)
    try:
        return await AnalyticsService.get_alert_fatigue(db, org_id)
    except Exception as e:
        logger.error("Failed to fetch alert fatigue statistics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch alert fatigue trends: {str(e)}"
        )


@router.post("/report/schedule", status_code=status.HTTP_201_CREATED)
async def schedule_analytics_report(
    config: Dict[str, Any],
    current_user: TokenPayload = Depends(get_current_user_payload)
) -> Dict[str, str]:
    """Registers a scheduled daily/weekly/monthly report configuration."""
    org_id = get_tenant_uuid(current_user)
    
    email = config.get("email")
    frequency = config.get("frequency") # "daily", "weekly", "monthly"
    if not email or not frequency:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and frequency are required parameters."
        )

    # Save configuration to logs directory to mock persistence
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "logs", "scheduled_reports")
    os.makedirs(log_dir, exist_ok=True)
    config_file = os.path.join(log_dir, "config.json")
    
    current_config = []
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                current_config = json.load(f)
        except Exception:
            pass
            
    record = {
        "id": str(uuid.uuid4()),
        "org_id": str(org_id),
        "user_id": current_user.sub,
        "email": email,
        "frequency": frequency,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    current_config.append(record)
    
    try:
        with open(config_file, "w") as f:
            json.dump(current_config, f, indent=2)
    except Exception as e:
        logger.error("Failed to persist scheduled report configuration", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule report."
        )

    return {"status": "scheduled", "message": f"Report successfully scheduled for {email} ({frequency})."}


@router.websocket("/ws")
async def websocket_analytics(
    websocket: WebSocket,
    token: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """WebSocket endpoint streaming real-time KPI metrics."""
    await websocket.accept()
    
    # Authenticate JWT token
    from app.api.v1.routers.chat import authenticate_ws
    user_payload = await authenticate_ws(token, db)
    if not user_payload:
        logger.warning("Analytics WS Connection rejected: Authentication failed")
        await websocket.close(code=1008) # Policy Violation
        return

    org_id = uuid.UUID(user_payload.tenant_id)
    
    try:
        while True:
            # Fetch KPIs
            kpis = await AnalyticsService.get_realtime_kpis(db, org_id)
            await websocket.send_text(json.dumps(kpis))
            await asyncio.sleep(5) # stream every 5s
    except WebSocketDisconnect:
        logger.info("Analytics WebSocket disconnected")
    except Exception as e:
        logger.error("Error in analytics websocket session", error=str(e))
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
