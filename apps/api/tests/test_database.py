import datetime
import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError, IntegrityError

from app.models.schema_models import (
    Organization, User, Role, Permission, UserRole, RolePermission,
    Camera, VideoSegment, DetectedObject, Event, SearchQuery, AuditLog
)

def test_crud_operations(db_session, tenant_context):
    """Test standard CRUD operations for all tables."""
    # 1. Create Organization
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Test Organization")
    db_session.add(org)
    tenant_context(db_session, org_id=org_id)
    db_session.flush()
    assert org.id is not None

    # 2. Create User
    user = User(
        org_id=org.id,
        email="user@test.org",
        hashed_password="hashedpassword123",
        is_active=True
    )
    db_session.add(user)
    db_session.flush()
    assert user.id is not None

    # Update context with user ID too
    tenant_context(db_session, org_id=org.id, user_id=user.id)

    # 3. Create Role & Permission
    role = Role(org_id=org.id, name="Viewer", description="View only role")
    perm = Permission(name="camera:read", description="Read camera streams")
    db_session.add_all([role, perm])
    db_session.flush()

    # Join User/Role and Role/Permission
    user_role = UserRole(user_id=user.id, role_id=role.id)
    role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
    db_session.add_all([user_role, role_perm])
    db_session.flush()

    # 4. Camera Insert/Update/Delete
    camera = Camera(
        org_id=org.id,
        name="Lobby Camera",
        location="Front Desk",
        rtsp_url="rtsp://admin:pass@10.0.0.10/stream",
        status="active"
    )
    db_session.add(camera)
    db_session.flush()

    # Update Camera
    camera.status = "offline"
    db_session.flush()

    # Query Camera
    db_camera = db_session.query(Camera).filter(Camera.id == camera.id).first()
    assert db_camera.status == "offline"

    # Soft Delete Camera
    db_camera.deleted_at = datetime.datetime.now(datetime.timezone.utc)
    db_session.flush()
    assert db_camera.deleted_at is not None

    # 5. Video Segment & Detected Object
    segment_id = uuid.uuid4()
    start_time = datetime.datetime(2026, 6, 12, 10, 0, 0, tzinfo=datetime.timezone.utc)
    end_time = start_time + datetime.timedelta(minutes=5)
    
    segment = VideoSegment(
        id=segment_id,
        org_id=org.id,
        camera_id=camera.id,
        s3_key="segments/test.mp4",
        start_time=start_time,
        end_time=end_time,
        duration_ms=300000,
        fps=30,
        resolution="1920x1080",
        file_size_bytes=50_000_000,
        processing_status="completed"
    )
    db_session.add(segment)
    db_session.flush()

    detected_obj = DetectedObject(
        org_id=org.id,
        segment_id=segment.id,
        segment_start_time=segment.start_time,
        frame_number=150,
        timestamp_ms=5000,
        class_label="person",
        confidence=0.92,
        bbox_x=0.12,
        bbox_y=0.34,
        bbox_w=0.15,
        bbox_h=0.45
    )
    db_session.add(detected_obj)
    db_session.flush()

    # 6. Event Hypertable
    event_id = uuid.uuid4()
    event = Event(
        id=event_id,
        org_id=org.id,
        camera_id=camera.id,
        event_type="intrusion",
        severity="critical",
        start_time=start_time,
        end_time=end_time,
        event_metadata={"source_type": "camera", "confidence_threshold": 0.85},
        thumbnail_s3_key="thumbnails/test.jpg"
    )
    db_session.add(event)
    db_session.flush()

    # 7. Vector Search Query
    dummy_embedding = [0.1] * 512
    search_query = SearchQuery(
        org_id=org.id,
        user_id=user.id,
        query_text="suspicious activity",
        query_embedding=dummy_embedding,
        results_count=3,
        latency_ms=45
    )
    db_session.add(search_query)
    db_session.flush()

    # Asserts
    assert db_session.query(VideoSegment).filter(VideoSegment.id == segment.id).count() == 1
    assert db_session.query(DetectedObject).filter(DetectedObject.id == detected_obj.id).count() == 1
    assert db_session.query(Event).filter(Event.id == event.id).count() == 1
    assert db_session.query(SearchQuery).filter(SearchQuery.id == search_query.id).count() == 1


def test_row_level_security(db_session, tenant_context):
    """Test tenant isolation via Row-Level Security policies."""
    # Create Org A
    org_a_id = uuid.uuid4()
    org_a = Organization(id=org_a_id, name="Org A")
    db_session.add(org_a)
    tenant_context(db_session, org_id=org_a_id)
    db_session.flush()

    # Create Org B
    org_b_id = uuid.uuid4()
    org_b = Organization(id=org_b_id, name="Org B")
    db_session.add(org_b)
    tenant_context(db_session, org_id=org_b_id)
    db_session.flush()

    # Insert Camera under Org A
    tenant_context(db_session, org_id=org_a_id)
    camera_a = Camera(
        org_id=org_a.id,
        name="Org A Camera",
        location="Lobby A",
        rtsp_url="rtsp://server/a",
        status="active"
    )
    db_session.add(camera_a)
    db_session.flush()

    # Insert Camera under Org B
    tenant_context(db_session, org_id=org_b_id)
    camera_b = Camera(
        org_id=org_b.id,
        name="Org B Camera",
        location="Lobby B",
        rtsp_url="rtsp://server/b",
        status="active"
    )
    db_session.add(camera_b)
    db_session.flush()

    # 1. Query with Tenant A context: Should return Org A camera and NOT Org B camera
    tenant_context(db_session, org_id=org_a.id)
    cameras_a = db_session.query(Camera).all()
    assert len(cameras_a) == 1
    assert cameras_a[0].name == "Org A Camera"

    # 2. Query with Tenant B context: Should return Org B camera and NOT Org A camera
    tenant_context(db_session, org_id=org_b.id)
    cameras_b = db_session.query(Camera).all()
    assert len(cameras_b) == 1
    assert cameras_b[0].name == "Org B Camera"

    # 3. Verify INSERT RLS: Attempt to insert a camera with Org A's ID while under Org B context
    # This should fail the RLS policy check because the tenant context is org_b but we're trying to write org_a
    # PostgreSQL blocks this write because the policy USING clause is violated
    with pytest.raises((IntegrityError, ProgrammingError, sa.exc.InternalError)):
        bad_camera = Camera(
            org_id=org_a.id,
            name="Breach Camera",
            location="Hack Office",
            rtsp_url="rtsp://server/bad",
            status="active"
        )
        db_session.add(bad_camera)
        db_session.flush()


def test_pii_encryption(db_session, tenant_context):
    """Test transparent PII encryption for RTSP URL."""
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Crypt Corp")
    db_session.add(org)
    tenant_context(db_session, org_id=org_id)
    db_session.flush()

    raw_url = "rtsp://admin:secretpassword@10.0.0.12:554/stream1"
    camera = Camera(
        org_id=org.id,
        name="Secure Cam",
        location="Safe Room",
        rtsp_url=raw_url,
        status="active"
    )
    db_session.add(camera)
    db_session.flush()

    # Query back via ORM: Should be automatically decrypted into plain text
    db_camera = db_session.query(Camera).filter(Camera.id == camera.id).first()
    assert db_camera.rtsp_url == raw_url

    # Query raw database directly: Value in DB must be encrypted ciphertext
    raw_query = db_session.execute(
        sa.text("SELECT rtsp_url FROM cameras WHERE id = :id"),
        {"id": camera.id}
    ).scalar()
    
    assert raw_query != raw_url
    assert raw_query.startswith("gAAAAA") # Standard Fernet ciphertext prefix


def test_audit_logs_and_immutability(db_session, tenant_context):
    """Test that DML logs are captured and audit logs are append-only."""
    # Insert Organization
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Audit Inc")
    db_session.add(org)
    tenant_context(db_session, org_id=org_id)
    db_session.flush()
    
    # Verify audit log recorded the insert of Organization
    audit_org = db_session.query(AuditLog).filter(
        AuditLog.table_name == "organizations",
        AuditLog.action == "INSERT"
    ).filter(
        AuditLog.new_data["id"].astext == str(org.id)
    ).first()
    assert audit_org is not None
    assert audit_org.new_data["name"] == "Audit Inc"

    # Set context
    tenant_context(db_session, org_id=org.id)

    # Insert Camera
    camera = Camera(
        org_id=org.id,
        name="Audit Cam",
        location="Server Room",
        rtsp_url="rtsp://audit/cam",
        status="active"
    )
    db_session.add(camera)
    db_session.flush()

    # Verify audit log recorded insert of Camera
    audit_cam_ins = db_session.query(AuditLog).filter(
        AuditLog.table_name == "cameras",
        AuditLog.action == "INSERT",
        AuditLog.org_id == org.id
    ).first()
    assert audit_cam_ins is not None
    assert audit_cam_ins.new_data["name"] == "Audit Cam"

    # Update Camera: Should trigger an UPDATE audit record
    camera.name = "Updated Audit Cam"
    db_session.flush()

    audit_cam_upd = db_session.query(AuditLog).filter(
        AuditLog.table_name == "cameras",
        AuditLog.action == "UPDATE",
        AuditLog.org_id == org.id
    ).first()
    assert audit_cam_upd is not None
    assert audit_cam_upd.old_data["name"] == "Audit Cam"
    assert audit_cam_upd.new_data["name"] == "Updated Audit Cam"

    # Test audit log immutability: Attempt to delete an audit log row
    # The protect_audit_log database trigger should block updates/deletes and raise an exception.
    with pytest.raises((ProgrammingError, sa.exc.InternalError)) as excinfo:
        db_session.delete(audit_org)
        db_session.flush()
    assert "Audit log is immutable and append-only" in str(excinfo.value)


def test_explain_index_usage(db_session, tenant_context):
    """Assert index usage in EXPLAIN plans for time-series filters, foreign keys, and unique keys."""
    # Seed a basic set of data to make sure planner can analyze
    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Index Testing")
    db_session.add(org)
    tenant_context(db_session, org_id=org_id)
    db_session.flush()
    
    tenant_context(db_session, org_id=org.id)

    user = User(
        org_id=org.id,
        email="index.user@test.org",
        hashed_password="password",
        is_active=True
    )
    db_session.add(user)
    
    camera = Camera(
        org_id=org.id,
        name="Index Cam",
        location="Zone A",
        rtsp_url="rtsp://index/cam",
        status="active"
    )
    db_session.add(camera)
    db_session.flush()

    segment_id = uuid.uuid4()
    start_time = datetime.datetime(2026, 6, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
    end_time = start_time + datetime.timedelta(minutes=5)
    
    segment = VideoSegment(
        id=segment_id,
        org_id=org.id,
        camera_id=camera.id,
        s3_key="segments/index.mp4",
        start_time=start_time,
        end_time=end_time,
        duration_ms=300000,
        fps=30,
        resolution="1080p",
        file_size_bytes=10000000,
        processing_status="completed"
    )
    db_session.add(segment)
    db_session.flush()

    # 1. EXPLAIN query on unique email: should use the unique index scan
    explain_user = db_session.execute(
        sa.text("EXPLAIN SELECT * FROM users WHERE email = 'index.user@test.org'")
    ).all()
    explain_user_text = "\n".join([row[0] for row in explain_user])
    assert "Index Scan" in explain_user_text or "Index Cond" in explain_user_text

    # 2. EXPLAIN query on video segment start_time (BRIN index / Partition scan)
    # Note: On small test databases, Postgres planner might choose Seq Scan because table is empty,
    # but we can force it to test index usage by disabling sequential scans.
    db_session.execute(sa.text("SET LOCAL enable_seqscan = off"))
    
    explain_seg = db_session.execute(
        sa.text("EXPLAIN SELECT * FROM video_segments WHERE start_time >= '2026-06-15T00:00:00Z'::timestamptz")
    ).all()
    explain_seg_text = "\n".join([row[0] for row in explain_seg])
    # Assert that it either scanned a specific partition or used an index
    assert "video_segments_2026_06" in explain_seg_text  # Partition pruning successfully limited query to the target partition!

    # 3. EXPLAIN query on detected objects class_label (Index Scan)
    explain_obj = db_session.execute(
        sa.text("EXPLAIN SELECT * FROM detected_objects WHERE class_label = 'person'")
    ).all()
    explain_obj_text = "\n".join([row[0] for row in explain_obj])
    assert "Index Scan" in explain_obj_text or "Bitmap Index Scan" in explain_obj_text
