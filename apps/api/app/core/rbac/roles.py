from enum import Enum
from typing import Dict, Set

class RoleEnum(str, Enum):
    SUPER_ADMIN = "super_admin"
    ORG_ADMIN = "org_admin"
    OPERATOR = "operator"
    ANALYST = "analyst"
    VIEWER = "viewer"

class PermissionEnum(str, Enum):
    CAMERA_READ = "camera:read"
    CAMERA_WRITE = "camera:write"
    VIDEO_EXPORT = "video:export"
    ALERT_MANAGE = "alert:manage"
    QUERY_EXECUTE = "query:execute"
    SYSTEM_ADMIN = "system:admin"

# Mapping roles to their permissions
ROLE_PERMISSIONS: Dict[RoleEnum, Set[PermissionEnum]] = {
    RoleEnum.SUPER_ADMIN: {
        PermissionEnum.CAMERA_READ,
        PermissionEnum.CAMERA_WRITE,
        PermissionEnum.VIDEO_EXPORT,
        PermissionEnum.ALERT_MANAGE,
        PermissionEnum.QUERY_EXECUTE,
        PermissionEnum.SYSTEM_ADMIN,
    },
    RoleEnum.ORG_ADMIN: {
        PermissionEnum.CAMERA_READ,
        PermissionEnum.CAMERA_WRITE,
        PermissionEnum.VIDEO_EXPORT,
        PermissionEnum.ALERT_MANAGE,
        PermissionEnum.QUERY_EXECUTE,
    },
    RoleEnum.OPERATOR: {
        PermissionEnum.CAMERA_READ,
        PermissionEnum.ALERT_MANAGE,
    },
    RoleEnum.ANALYST: {
        PermissionEnum.CAMERA_READ,
        PermissionEnum.VIDEO_EXPORT,
        PermissionEnum.QUERY_EXECUTE,
    },
    RoleEnum.VIEWER: {
        PermissionEnum.CAMERA_READ,
    },
}

def has_permission_in_role(role: str, permission: str) -> bool:
    """Checks if a role has a specific permission."""
    try:
        r_enum = RoleEnum(role)
        p_enum = PermissionEnum(permission)
        return p_enum in ROLE_PERMISSIONS.get(r_enum, set())
    except ValueError:
        return False
