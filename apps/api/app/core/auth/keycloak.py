import uuid
import logging
from typing import Optional, Dict, Any
import redis.asyncio as aioredis
from app.core.config import settings
from app.db.session import async_session_maker
from app.models.schema_models import AuditLog

logger = logging.getLogger("visionquery.auth")

# Redis client factory
def get_redis_client() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)

async def is_token_blacklisted(payload: Dict[str, Any]) -> bool:
    """Checks if a token's jti is in the Redis blacklist."""
    jti = payload.get("jti")
    if not jti:
        return False
    
    redis = get_redis_client()
    try:
        exists = await redis.exists(f"token:blacklist:{jti}")
        return exists > 0
    except Exception as e:
        logger.error("Failed to query Redis blacklist: %s", str(e))
        return False
    finally:
        await redis.close()

async def blacklist_token(payload: Dict[str, Any], expires_in: int = 3600) -> None:
    """Adds a token's jti to the Redis blacklist with an expiry time."""
    jti = payload.get("jti")
    if not jti:
        return
    
    redis = get_redis_client()
    try:
        await redis.setex(f"token:blacklist:{jti}", expires_in, "revoked")
        logger.info("Token blacklisted: jti=%s", jti)
    except Exception as e:
        logger.error("Failed to blacklist token in Redis: %s", str(e))
    finally:
        await redis.close()

async def is_account_locked_out(username: str) -> bool:
    """Checks if a user is currently locked out after too many failed logins."""
    redis = get_redis_client()
    try:
        locked = await redis.exists(f"lockout:{username}")
        return locked > 0
    except Exception as e:
        logger.error("Failed to check lockout status in Redis: %s", str(e))
        return False
    finally:
        await redis.close()

async def increment_failed_attempts(username: str) -> int:
    """Increments failed login attempts and applies lockout if threshold is exceeded (5 attempts)."""
    redis = get_redis_client()
    try:
        key = f"failed_attempts:{username}"
        attempts = await redis.incr(key)
        if attempts == 1:
            await redis.expire(key, 600) # Reset attempt count after 10 mins
        
        if attempts >= 5:
            # Lock out for 15 minutes (900 seconds)
            await redis.setex(f"lockout:{username}", 900, "locked")
            await redis.delete(key) # Clear failure attempts count since they are now locked out
            logger.warning("User %s has been locked out due to 5 failed login attempts.", username)
            return attempts
        return attempts
    except Exception as e:
        logger.error("Failed to increment login failures in Redis: %s", str(e))
        return 0
    finally:
        await redis.close()

async def reset_failed_attempts(username: str) -> None:
    """Resets failed login attempts and lockout for a user."""
    redis = get_redis_client()
    try:
        await redis.delete(f"failed_attempts:{username}")
        await redis.delete(f"lockout:{username}")
    except Exception as e:
        logger.error("Failed to reset login failures in Redis: %s", str(e))
    finally:
        await redis.close()

async def log_auth_event(
    org_id: Optional[str],
    user_id: Optional[str],
    action: str,
    ip_address: Optional[str],
    details: Dict[str, Any]
) -> None:
    """Inserts a secure audit event log into the PostgreSQL audit_log table."""
    try:
        # Convert IDs to UUIDs if valid
        org_uuid = uuid.UUID(org_id) if org_id else None
        user_uuid = uuid.UUID(user_id) if user_id else None
    except ValueError:
        logger.warning("Invalid UUID formats passed to log_auth_event: org=%s user=%s", org_id, user_id)
        org_uuid = None
        user_uuid = None

    async with async_session_maker() as session:
        try:
            audit = AuditLog(
                org_id=org_uuid,
                user_id=user_uuid,
                table_name="auth",
                action=action,
                old_data=None,
                new_data=details,
                query_text=f"Auth Event: {action}",
                ip_address=ip_address
            )
            session.add(audit)
            await session.commit()
            logger.info("Audit log written: action=%s user=%s", action, user_id)
        except Exception as e:
            logger.error("Failed to write auth event to audit log database: %s", str(e))
            await session.rollback()
