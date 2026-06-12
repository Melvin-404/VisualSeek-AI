from fastapi import Depends, HTTPException, status
from typing import List

from app.core.security import get_current_user_payload, TokenPayload
from app.core.rbac.roles import has_permission_in_role

class PermissionChecker:
    """Dependency checker to enforce specific permissions on API routes."""
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    def __call__(self, current_user: TokenPayload = Depends(get_current_user_payload)) -> TokenPayload:
        # Check if the user has the permission directly in scopes/claims
        if current_user.scopes and self.required_permission in current_user.scopes:
            return current_user
        
        # Check if the user's role grants this permission
        if current_user.role and has_permission_in_role(current_user.role, self.required_permission):
            return current_user
            
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission '{self.required_permission}' is required to access this resource."
        )

def require_permission(permission: str):
    """Convenience helper to enforce permission requirements."""
    return Depends(PermissionChecker(permission))
