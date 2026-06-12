import datetime
import uuid
from typing import Optional, Dict, Any, List
from pydantic import Field, EmailStr

from app.schemas.base import BaseSchema


# Organization Schemas
class OrganizationBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=255)


class OrganizationResponse(OrganizationBase):
    id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: Optional[datetime.datetime] = None


# User Schemas
class UserBase(BaseSchema):
    email: EmailStr
    is_active: bool = True


class UserCreate(UserBase):
    org_id: uuid.UUID
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseSchema):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class UserResponse(UserBase):
    id: uuid.UUID
    org_id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: Optional[datetime.datetime] = None


# Role Schemas
class RoleBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class RoleCreate(RoleBase):
    org_id: uuid.UUID


class RoleUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class RoleResponse(RoleBase):
    id: uuid.UUID
    org_id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: Optional[datetime.datetime] = None


# Permission Schemas
class PermissionBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class PermissionResponse(PermissionBase):
    id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: Optional[datetime.datetime] = None


# UserRole & RolePermission Joint Response Schemas
class UserRoleSchema(BaseSchema):
    user_id: uuid.UUID
    role_id: uuid.UUID


class RolePermissionSchema(BaseSchema):
    role_id: uuid.UUID
    permission_id: uuid.UUID


# Camera Schemas
class CameraBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    location: str = Field(..., min_length=1, max_length=255)
    rtsp_url: str = Field(..., min_length=1)
    status: str = Field("offline", max_length=50)


class CameraCreate(CameraBase):
    org_id: uuid.UUID


class CameraUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    location: Optional[str] = Field(None, min_length=1, max_length=255)
    rtsp_url: Optional[str] = Field(None, min_length=1)
    status: Optional[str] = Field(None, max_length=50)


class CameraResponse(CameraBase):
    id: uuid.UUID
    org_id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: Optional[datetime.datetime] = None


# VideoSegment Schemas
class VideoSegmentBase(BaseSchema):
    s3_key: str = Field(..., min_length=1, max_length=512)
    start_time: datetime.datetime
    end_time: datetime.datetime
    duration_ms: int = Field(..., ge=0)
    fps: int = Field(..., ge=1)
    resolution: str = Field(..., min_length=1, max_length=50)
    file_size_bytes: int = Field(..., ge=0)
    processing_status: str = Field("pending", max_length=50)


class VideoSegmentCreate(VideoSegmentBase):
    id: uuid.UUID
    org_id: uuid.UUID
    camera_id: uuid.UUID


class VideoSegmentUpdate(BaseSchema):
    s3_key: Optional[str] = Field(None, min_length=1, max_length=512)
    end_time: Optional[datetime.datetime] = None
    duration_ms: Optional[int] = Field(None, ge=0)
    fps: Optional[int] = Field(None, ge=1)
    resolution: Optional[str] = Field(None, min_length=1, max_length=50)
    file_size_bytes: Optional[int] = Field(None, ge=0)
    processing_status: Optional[str] = Field(None, max_length=50)


class VideoSegmentResponse(VideoSegmentBase):
    id: uuid.UUID
    org_id: uuid.UUID
    camera_id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: Optional[datetime.datetime] = None


# DetectedObject Schemas
class DetectedObjectBase(BaseSchema):
    frame_number: int = Field(..., ge=0)
    timestamp_ms: int = Field(..., ge=0)
    class_label: str = Field(..., min_length=1, max_length=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox_x: float = Field(...)
    bbox_y: float = Field(...)
    bbox_w: float = Field(..., ge=0.0)
    bbox_h: float = Field(..., ge=0.0)
    track_id: Optional[int] = None


class DetectedObjectCreate(DetectedObjectBase):
    org_id: uuid.UUID
    segment_id: uuid.UUID
    segment_start_time: datetime.datetime


class DetectedObjectUpdate(BaseSchema):
    frame_number: Optional[int] = Field(None, ge=0)
    timestamp_ms: Optional[int] = Field(None, ge=0)
    class_label: Optional[str] = Field(None, min_length=1, max_length=100)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    bbox_x: Optional[float] = None
    bbox_y: Optional[float] = None
    bbox_w: Optional[float] = Field(None, ge=0.0)
    bbox_h: Optional[float] = Field(None, ge=0.0)
    track_id: Optional[int] = None


class DetectedObjectResponse(DetectedObjectBase):
    id: uuid.UUID
    org_id: uuid.UUID
    segment_id: uuid.UUID
    segment_start_time: datetime.datetime
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: Optional[datetime.datetime] = None


# Event Schemas
class EventBase(BaseSchema):
    event_type: str = Field(..., min_length=1, max_length=100)
    severity: str = Field("info", max_length=50)
    end_time: datetime.datetime
    metadata: Dict[str, Any]
    thumbnail_s3_key: str = Field(..., min_length=1, max_length=512)


class EventCreate(EventBase):
    id: uuid.UUID
    org_id: uuid.UUID
    camera_id: uuid.UUID
    start_time: datetime.datetime


class EventUpdate(BaseSchema):
    event_type: Optional[str] = Field(None, min_length=1, max_length=100)
    severity: Optional[str] = Field(None, max_length=50)
    end_time: Optional[datetime.datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    thumbnail_s3_key: Optional[str] = Field(None, min_length=1, max_length=512)


class EventResponse(EventBase):
    id: uuid.UUID
    org_id: uuid.UUID
    camera_id: uuid.UUID
    start_time: datetime.datetime
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: Optional[datetime.datetime] = None


# SearchQuery Schemas
class SearchQueryBase(BaseSchema):
    query_text: str = Field(..., min_length=1)
    query_embedding: List[float] = Field(..., min_length=512, max_length=512)
    results_count: int = Field(..., ge=0)
    latency_ms: int = Field(..., ge=0)


class SearchQueryCreate(SearchQueryBase):
    org_id: uuid.UUID
    user_id: uuid.UUID


class SearchQueryResponse(SearchQueryBase):
    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
    updated_at: datetime.datetime
    deleted_at: Optional[datetime.datetime] = None


# AuditLog Schemas
class AuditLogResponse(BaseSchema):
    id: uuid.UUID
    org_id: Optional[uuid.UUID] = None
    table_name: str
    action: str
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None
    query_text: str
    user_id: Optional[uuid.UUID] = None
    ip_address: Optional[str] = None
    created_at: datetime.datetime
