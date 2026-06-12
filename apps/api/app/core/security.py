import hashlib
import hmac
import os
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.session import get_db

logger = logging.getLogger("visionquery.security")

# OAuth2 and API Key schemes
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# PBKDF2 Settings
PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 600000


class TokenPayload(BaseModel):
    """Pydantic model representing unified authentication identity payload fields."""
    sub: str = Field(..., description="User ID, Service ID or identifier")
    tenant_id: str = Field(..., description="Organization/Tenant ID")
    role: str = Field("viewer", description="Active RBAC Role")
    roles: List[str] = Field(default_factory=list, description="All assigned roles")
    scopes: List[str] = Field(default_factory=list, description="Assigned scopes/permissions")
    exp: float = Field(..., description="Expiration timestamp")


def hash_password(password: str) -> str:
    """Generates a secure PBKDF2-SHA256 hash formatted as pbkdf2:sha256:600000$salt$hash."""
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS
    )
    return f"pbkdf2:{PBKDF2_ALGORITHM}:{PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against a formatted PBKDF2 hash."""
    if not hashed_password.startswith("pbkdf2:"):
        return plain_password == hashed_password

    try:
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False
        
        algo_iter, salt, target_hash_hex = parts
        _, algo, iterations_str = algo_iter.split(":")
        iterations = int(iterations_str)

        dk = hashlib.pbkdf2_hmac(
            algo,
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations
        )
        return hmac.compare_digest(dk.hex(), target_hash_hex)
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generates an HS256 encoded JWT token (for backward compatibility/local test flows)."""
    import jwt as pyjwt
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire.timestamp()})
    
    # Ensure standard fields are populated
    if "tenant_id" not in to_encode and "org_id" in to_encode:
        to_encode["tenant_id"] = to_encode["org_id"]
        
    return pyjwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def hash_api_key(api_key: str) -> str:
    """Hashes a service API key using SHA-256."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


async def get_current_user_payload(
    token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Depends(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> TokenPayload:
    """Dependency asserting credential validity and returning active user/service payload.
    
    Supports both Keycloak/Local OIDC tokens (OAuth2 Bearer) and Service API Keys (X-API-Key).
    """
    # 1. Handle API Key Auth (Service-to-Service)
    if api_key:
        from app.models.schema_models import ApiKey
        key_hash = hash_api_key(api_key)
        
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
        res = await db.execute(stmt)
        api_key_record = res.scalars().first()
        
        if api_key_record:
            # Check expiration
            if api_key_record.expires_at and api_key_record.expires_at < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key has expired."
                )
            
            # Successful S2S Auth
            return TokenPayload(
                sub=str(api_key_record.id),
                tenant_id=str(api_key_record.org_id),
                role="service",
                roles=["service"],
                scopes=api_key_record.scopes,
                exp=api_key_record.expires_at.timestamp() if api_key_record.expires_at else float("inf")
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key."
            )

    # 2. Handle OIDC / Bearer Token Auth
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        from app.core.auth.jwt import decode_and_verify_token
        from app.core.auth.keycloak import is_token_blacklisted
        
        payload = decode_and_verify_token(token)
        
        # Check blacklist in Redis (revocation)
        if await is_token_blacklisted(payload):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been blacklisted/revoked.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Parse sub and exp
        sub = payload.get("sub")
        exp = payload.get("exp")
        if not sub or not exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing required fields sub or exp."
            )
            
        # Parse roles
        roles = []
        if "realm_access" in payload and isinstance(payload["realm_access"], dict):
            roles = payload["realm_access"].get("roles", [])
        elif "role" in payload:
            roles = [payload["role"]]
        elif "roles" in payload:
            roles = payload["roles"]
            
        # Resolve active role
        from app.core.rbac.roles import RoleEnum
        valid_roles = [r for r in roles if r in RoleEnum.__members__.values()]
        role = valid_roles[0] if valid_roles else "viewer"
        
        # Parse scopes / permissions
        scopes = []
        if "scope" in payload:
            scopes = payload["scope"].split(" ")
        elif "scopes" in payload:
            scopes = payload["scopes"]
            
        # Parse tenant / organization
        tenant_id = payload.get("tenant_id") or payload.get("org_id")
        
        # If tenant_id is not present in token, resolve from DB for local tests
        if not tenant_id:
            from app.models.schema_models import User
            try:
                user_uuid = uuid.UUID(sub)
                user_stmt = select(User).where(User.id == user_uuid)
                user_res = await db.execute(user_stmt)
                db_user = user_res.scalars().first()
                if db_user:
                    tenant_id = str(db_user.org_id)
            except ValueError:
                pass
                
        # Default fallback tenant
        if not tenant_id:
            tenant_id = "00000000-0000-0000-0000-000000000000"
            
        return TokenPayload(
            sub=str(sub),
            tenant_id=str(tenant_id),
            role=role,
            roles=roles,
            scopes=scopes,
            exp=float(exp)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Authentication failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials or token expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
