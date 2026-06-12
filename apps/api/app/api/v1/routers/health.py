from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
import structlog
from typing import Dict, Any

from app.core.config import settings
from app.db.session import get_db

logger = structlog.get_logger("health")
router = APIRouter(prefix="/health", tags=["Health Checks"])


@router.get("/live", status_code=status.HTTP_200_OK, response_model=Dict[str, str])
async def liveness_check() -> Dict[str, str]:
    """Basic liveness probe verifying that the API process is running."""
    return {"status": "alive"}


@router.get("/ready", status_code=status.HTTP_200_OK, response_model=Dict[str, Any])
async def readiness_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Readiness probe checking connectivity to PostgreSQL and Redis databases."""
    db_ok = False
    redis_ok = False
    details = {}

    # 1. Probe Postgres
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
        details["postgres"] = "healthy"
    except Exception as e:
        logger.error("Readiness check: PostgreSQL connection failed", error=str(e))
        details["postgres"] = "unhealthy"

    # 2. Probe Redis
    try:
        client = aioredis.from_url(settings.REDIS_URL, socket_timeout=2.0)
        await client.ping()
        await client.aclose()
        redis_ok = True
        details["redis"] = "healthy"
    except Exception as e:
        logger.error("Readiness check: Redis connection failed", error=str(e))
        details["redis"] = "unhealthy"

    # Evaluate readiness
    if not (db_ok and redis_ok):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unready", "services": details}
        )

    return {"status": "ready", "services": details}


@router.get("/gpu", status_code=status.HTTP_200_OK, response_model=Dict[str, Any])
async def gpu_check() -> Dict[str, Any]:
    """Probes GPU compute parameters, returning NVIDIA H200 specifications or active torch details."""
    stats = {}
    
    # 1. Check if PyTorch detects CUDA
    try:
        cuda_available = torch.cuda.is_available() if HAS_TORCH else False
        stats["cuda_available"] = cuda_available
        
        if cuda_available and HAS_TORCH:
            device_id = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(device_id)
            device_props = torch.cuda.get_device_properties(device_id)
            free_mem, total_mem = torch.cuda.mem_get_info(device_id)
            
            stats.update({
                "gpu_name": device_name,
                "compute_capability": f"{device_props.major}.{device_props.minor}",
                "multi_processor_count": device_props.multi_processor_count,
                "memory_total_bytes": total_mem,
                "memory_free_bytes": free_mem,
                "memory_used_bytes": total_mem - free_mem,
                "status": "active"
            })
            logger.info("GPU stats retrieved successfully from Torch CUDA runtime", gpu_name=device_name)
        else:
            # Fallback to Mock statistics representing a local NVIDIA GeForce RTX 4060 GPU
            # NVIDIA GeForce RTX 4060 has 8 GB memory (approx 8,589,934,592 bytes)
            total_mock_mem = 8 * 1024 * 1024 * 1024
            used_mock_mem = int(total_mock_mem * 0.64) # simulate 64% load
            free_mock_mem = total_mock_mem - used_mock_mem
            
            stats.update({
                "gpu_name": "NVIDIA GeForce RTX 4060",
                "compute_capability": "8.9",
                "multi_processor_count": 24,
                "memory_total_bytes": total_mock_mem,
                "memory_free_bytes": free_mock_mem,
                "memory_used_bytes": used_mock_mem,
                "status": "mocked (CUDA unavailable in current host environment)"
            })
            logger.warning("CUDA unavailable. Returning mock NVIDIA GeForce RTX 4060 GPU statistics.")
            
    except Exception as e:
        logger.error("GPU check failed: error reading torch parameters", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve GPU status: {e}"
        )

    return stats
