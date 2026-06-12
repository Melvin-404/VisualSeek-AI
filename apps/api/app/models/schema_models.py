import uuid
from typing import Optional, Dict, Any
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, EncryptedString


class Organization(Base, TimestampMixin):
    """Organization model representing tenants."""
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)


class User(Base, TimestampMixin):
    """User model with RBAC capabilities."""
    __tablename__ = "users"
    __table_args__ = (
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.Index("ix_users_org_id", "org_id"),
        sa.Index("ix_users_email", "email", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), default=True, server_default=sa.text("true"), nullable=False)


class Role(Base, TimestampMixin):
    """Role model for RBAC."""
    __tablename__ = "roles"
    __table_args__ = (
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("org_id", "name", name="uq_roles_org_id_name"),
        sa.Index("ix_roles_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(sa.Text(), nullable=True)


class Permission(Base, TimestampMixin):
    """Permission model representing individual capabilities."""
    __tablename__ = "permissions"
    __table_args__ = (
        sa.Index("ix_permissions_name", "name", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(sa.Text(), nullable=True)


class UserRole(Base):
    """Association table between Users and Roles."""
    __tablename__ = "user_roles"
    __table_args__ = (
        sa.PrimaryKeyConstraint("user_id", "role_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.Index("ix_user_roles_role_id", "role_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class RolePermission(Base):
    """Association table between Roles and Permissions."""
    __tablename__ = "role_permissions"
    __table_args__ = (
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.Index("ix_role_permissions_permission_id", "permission_id"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    permission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class Camera(Base, TimestampMixin):
    """Camera Model."""
    __tablename__ = "cameras"
    __table_args__ = (
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.Index("ix_cameras_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    location: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    rtsp_url: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(50), default="offline", server_default="offline", nullable=False)


class VideoSegment(Base, TimestampMixin):
    """VideoSegment model. Range-partitioned by month on start_time."""
    __tablename__ = "video_segments"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", "start_time"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.Index("ix_video_segments_camera_id", "camera_id"),
        sa.Index("ix_video_segments_org_id", "org_id"),
        sa.Index("ix_video_segments_start_time_brin", "start_time", postgresql_using="brin"),
        {"postgresql_partition_by": "RANGE (start_time)"}
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    s3_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    start_time: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    end_time: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    fps: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    resolution: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    processing_status: Mapped[str] = mapped_column(sa.String(50), default="pending", server_default="pending", nullable=False)


class DetectedObject(Base, TimestampMixin):
    """DetectedObject model representing object inferences on segments."""
    __tablename__ = "detected_objects"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["segment_id", "segment_start_time"],
            ["video_segments.id", "video_segments.start_time"],
            ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.Index("ix_detected_objects_segment_id_start_time", "segment_id", "segment_start_time"),
        sa.Index("ix_detected_objects_org_id", "org_id"),
        sa.Index("ix_detected_objects_class_label", "class_label"),
        sa.Index("ix_detected_objects_track_id", "track_id"),
        sa.Index("ix_detected_objects_created_at_brin", "created_at", postgresql_using="brin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        primary_key=True,
        server_default=sa.func.now(),
        nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    segment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    segment_start_time: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    frame_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    class_label: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(sa.Double, nullable=False)
    bbox_x: Mapped[float] = mapped_column(sa.Double, nullable=False)
    bbox_y: Mapped[float] = mapped_column(sa.Double, nullable=False)
    bbox_w: Mapped[float] = mapped_column(sa.Double, nullable=False)
    bbox_h: Mapped[float] = mapped_column(sa.Double, nullable=False)
    track_id: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)


class Event(Base, TimestampMixin):
    """Event model representing security/operational alerts. Converted to a TimescaleDB hypertable."""
    __tablename__ = "events"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", "start_time"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.Index("ix_events_camera_id", "camera_id"),
        sa.Index("ix_events_org_id", "org_id"),
        sa.Index("ix_events_start_time_brin", "start_time", postgresql_using="brin"),
        sa.Index("ix_events_metadata_gin", "metadata", postgresql_using="gin"),
        sa.CheckConstraint(
            "metadata ? 'source_type' AND metadata ? 'confidence_threshold'",
            name="chk_event_metadata_keys"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    severity: Mapped[str] = mapped_column(sa.String(50), default="info", server_default="info", nullable=False)
    start_time: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    end_time: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    event_metadata: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)
    thumbnail_s3_key: Mapped[str] = mapped_column(sa.String(512), nullable=False)


class SearchQuery(Base, TimestampMixin):
    """SearchQuery model tracking vector queries."""
    __tablename__ = "search_queries"
    __table_args__ = (
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.Index("ix_search_queries_user_id", "user_id"),
        sa.Index("ix_search_queries_org_id", "org_id"),
        sa.Index("ix_search_queries_created_at_brin", "created_at", postgresql_using="brin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        primary_key=True,
        server_default=sa.func.now(),
        nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    query_text: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    query_embedding: Mapped[list] = mapped_column(ARRAY(sa.Float), nullable=False)
    results_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class AuditLog(Base):
    """Immutable Audit Log table."""
    __tablename__ = "audit_log"
    __table_args__ = (
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.Index("ix_audit_log_org_id", "org_id"),
        sa.Index("ix_audit_log_user_id", "user_id"),
        sa.Index("ix_audit_log_created_at_brin", "created_at", postgresql_using="brin"),
        sa.CheckConstraint("old_data IS NULL OR jsonb_typeof(old_data) = 'object'", name="chk_audit_old_data_object"),
        sa.CheckConstraint("new_data IS NULL OR jsonb_typeof(new_data) = 'object'", name="chk_audit_new_data_object"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    table_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    action: Mapped[str] = mapped_column(sa.String(50), nullable=False) # INSERT, UPDATE, DELETE
    old_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    new_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    query_text: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(sa.String(45), nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False
    )


class CameraAssignment(Base, TimestampMixin):
    """CameraAssignment model mapping operator users to specific cameras."""
    __tablename__ = "camera_assignments"
    __table_args__ = (
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.Index("ix_camera_assignments_user_id", "user_id"),
        sa.Index("ix_camera_assignments_camera_id", "camera_id"),
        sa.UniqueConstraint("user_id", "camera_id", name="uq_camera_assignments_user_camera"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class ApiKey(Base, TimestampMixin):
    """ApiKey model for service-to-service authentication."""
    __tablename__ = "api_keys"
    __table_args__ = (
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.Index("ix_api_keys_org_id", "org_id"),
        sa.Index("ix_api_keys_key_hash", "key_hash", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)  # list of scopes/permissions
    is_active: Mapped[bool] = mapped_column(sa.Boolean(), default=True, server_default=sa.text("true"), nullable=False)
    expires_at: Mapped[Optional[sa.DateTime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class CameraHealthLog(Base):
    """CameraHealthLog model tracking camera health over time."""
    __tablename__ = "camera_health_logs"
    __table_args__ = (
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.Index("ix_camera_health_org_id", "org_id"),
        sa.Index("ix_camera_health_timestamp_brin", "timestamp", postgresql_using="brin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    timestamp: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        primary_key=True,
        nullable=False
    )
    uptime_status: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    frame_drop_rate: Mapped[float] = mapped_column(sa.Double, nullable=False)
    detection_latency_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)

