from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, Optional
from pydantic import BaseModel, EmailStr

from app.core.security import verify_password, create_access_token
from app.db.session import get_db
from app.models.schema_models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    """Pydantic schema representing authentication requests."""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Pydantic schema representing successful login responses."""
    access_token: str
    token_type: str = "bearer"
    email: str
    tenant_id: str


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db)
) -> LoginResponse:
    """Authenticates a user via email and password, returning an access token and tenant context.
    
    Args:
        payload: Pydantic body containing email and password.
        db: Database async session.
        
    Returns:
        LoginResponse: JWT access token and user identity metadata.
    """
    # Query database for user
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account."
        )

    # Generate token payload
    token_data = {
        "sub": str(user.id),
        "tenant_id": str(user.org_id),
        "role": "user" # default role context
    }
    
    token = create_access_token(data=token_data)
    
    return LoginResponse(
        access_token=token,
        email=user.email,
        tenant_id=str(user.org_id)
    )
