import uuid
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import get_current_user_payload, TokenPayload
from app.core.rbac.roles import RoleEnum
from app.db.session import get_db
from app.models.schema_models import Camera, CameraAssignment

async def check_camera_access(
    camera_id: uuid.UUID,
    current_user: TokenPayload = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
) -> Camera:
    """Verifies that the current user has access to the specified camera.
    
    Enforces multi-tenancy (tenant ID matching) and operator camera assignment logic.
    
    Args:
        camera_id: UUID of the camera to check.
        current_user: The decoded JWT token payload.
        db: Database async session.
        
    Returns:
        Camera: The validated camera object if access is approved.
        
    Raises:
        HTTPException: 404 if camera is not found, 403 if access is denied.
    """
    # 1. Fetch camera
    stmt = select(Camera).where(Camera.id == camera_id)
    res = await db.execute(stmt)
    camera = res.scalars().first()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera with ID '{camera_id}' not found."
        )
        
    # 2. Super admin bypasses all isolation checks
    if current_user.role == RoleEnum.SUPER_ADMIN:
        return camera
        
    # 3. Organization check (multitenancy)
    user_tenant_uuid = uuid.UUID(current_user.tenant_id) if current_user.tenant_id else None
    if not user_tenant_uuid or camera.org_id != user_tenant_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to resources in another organization is denied."
        )
        
    # 4. Operator check: operators must be explicitly assigned to the camera
    if current_user.role == RoleEnum.OPERATOR:
        user_uuid = uuid.UUID(current_user.sub)
        assign_stmt = select(CameraAssignment).where(
            CameraAssignment.user_id == user_uuid,
            CameraAssignment.camera_id == camera_id
        )
        assign_res = await db.execute(assign_stmt)
        assignment = assign_res.scalars().first()
        
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operator is not assigned to this camera."
            )
            
    # 5. Other roles (org_admin, analyst, viewer) get access to all cameras in their org
    return camera
