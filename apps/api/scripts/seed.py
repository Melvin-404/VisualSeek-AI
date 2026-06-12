import datetime
import uuid
import random
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.schema_models import (
    Organization, User, Role, Permission, UserRole, RolePermission,
    Camera, VideoSegment, DetectedObject
)

def seed_database():
    """Seeds the database with test organization, RBAC, cameras, segments, and objects."""
    print("Connecting to database at:", settings.DATABASE_URL)
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Start a transaction block
        with session.begin():
            print("Creating organization and user context...")
            # 1. Create Organization
            org_id = uuid.uuid4()
            org = Organization(id=org_id, name="VisionQuery Test Corp")
            session.add(org)
            
            # 2. Create User
            user_id = uuid.uuid4()
            user = User(
                id=user_id,
                org_id=org_id,
                email="security.admin@visionquery.ai",
                hashed_password="pbkdf2:sha256:600000$supersecretpbkdf2hash",
                is_active=True
            )
            session.add(user)

            # Set tenant session variable for auditing triggers (user_id is not set yet during bootstrap)
            session.execute(text("SELECT set_config('app.current_org_id', :org_id, true)"), {"org_id": str(org_id)})
            
            # Flush org and user first to ensure user exists before setting app.current_user_id
            session.flush()
            
            # Set user session variable for subsequent operations
            session.execute(text("SELECT set_config('app.current_user_id', :user_id, true)"), {"user_id": str(user_id)})

            # 3. Create Roles & Permissions
            admin_role = Role(
                id=uuid.uuid4(),
                org_id=org_id,
                name="Organization Admin",
                description="Administrator for the organization."
            )
            session.add(admin_role)

            view_cameras_perm = Permission(
                id=uuid.uuid4(),
                name="camera:view",
                description="Ability to view camera streams and segments."
            )
            manage_cameras_perm = Permission(
                id=uuid.uuid4(),
                name="camera:manage",
                description="Ability to add or delete cameras."
            )
            session.add_all([view_cameras_perm, manage_cameras_perm])

            # Flush to get IDs
            session.flush()

            # Join User and Role
            user_role = UserRole(user_id=user_id, role_id=admin_role.id)
            session.add(user_role)

            # Join Role and Permissions
            role_perm1 = RolePermission(role_id=admin_role.id, permission_id=view_cameras_perm.id)
            role_perm2 = RolePermission(role_id=admin_role.id, permission_id=manage_cameras_perm.id)
            session.add_all([role_perm1, role_perm2])

            # 4. Insert 2 Cameras
            camera_a_id = uuid.uuid4()
            camera_a = Camera(
                id=camera_a_id,
                org_id=org_id,
                name="Front Entrance Gate",
                location="Building A - Main Lobby",
                rtsp_url="rtsp://admin:securepass123@192.168.1.50/live/ch1",
                status="active"
            )
            camera_b_id = uuid.uuid4()
            camera_b = Camera(
                id=camera_b_id,
                org_id=org_id,
                name="Back Parking Lot",
                location="Outdoor Lot - Section C",
                rtsp_url="rtsp://admin:parkingpass456@192.168.1.51/live/ch1",
                status="active"
            )
            session.add_all([camera_a, camera_b])
            session.flush()
            print("Successfully inserted 2 test cameras.")

            # 5. Insert 10 Video Segments (5 for Camera A, 5 for Camera B)
            # Spread times across June 2026
            base_time = datetime.datetime(2026, 6, 10, 10, 0, 0, tzinfo=datetime.timezone.utc)
            segments = []
            
            for idx in range(5):
                # Camera A Segments
                seg_a_id = uuid.uuid4()
                start_a = base_time + datetime.timedelta(hours=idx * 2)
                end_a = start_a + datetime.timedelta(minutes=5)
                seg_a = VideoSegment(
                    id=seg_a_id,
                    org_id=org_id,
                    camera_id=camera_a_id,
                    s3_key=f"segments/{org_id}/{camera_a_id}/{seg_a_id}.mp4",
                    start_time=start_a,
                    end_time=end_a,
                    duration_ms=300000,
                    fps=30,
                    resolution="1920x1080",
                    file_size_bytes=104857600 + (idx * 5000000), # ~100MB
                    processing_status="completed"
                )
                segments.append(seg_a)

                # Camera B Segments
                seg_b_id = uuid.uuid4()
                start_b = base_time + datetime.timedelta(hours=idx * 2 + 1)
                end_b = start_b + datetime.timedelta(minutes=5)
                seg_b = VideoSegment(
                    id=seg_b_id,
                    org_id=org_id,
                    camera_id=camera_b_id,
                    s3_key=f"segments/{org_id}/{camera_b_id}/{seg_b_id}.mp4",
                    start_time=start_b,
                    end_time=end_b,
                    duration_ms=300000,
                    fps=25,
                    resolution="1280x720",
                    file_size_bytes=52428800 + (idx * 3000000), # ~50MB
                    processing_status="completed"
                )
                segments.append(seg_b)

            session.add_all(segments)
            session.flush()
            print(f"Successfully inserted {len(segments)} test video segments.")

            # 6. Insert 50 Detected Objects (5 per video segment)
            class_labels = ["person", "car", "bicycle", "truck", "backpack"]
            objects_count = 0
            
            for segment in segments:
                for obj_idx in range(5):
                    obj_id = uuid.uuid4()
                    detected_obj = DetectedObject(
                        id=obj_id,
                        org_id=org_id,
                        segment_id=segment.id,
                        segment_start_time=segment.start_time,
                        frame_number=100 + (obj_idx * 150),
                        timestamp_ms=3300 + (obj_idx * 5000),
                        class_label=random.choice(class_labels),
                        confidence=round(random.uniform(0.75, 0.99), 4),
                        bbox_x=round(random.uniform(0.05, 0.45), 4),
                        bbox_y=round(random.uniform(0.05, 0.45), 4),
                        bbox_w=round(random.uniform(0.1, 0.4), 4),
                        bbox_h=round(random.uniform(0.1, 0.4), 4),
                        track_id=obj_idx + 1
                    )
                    session.add(detected_obj)
                    objects_count += 1
            
            session.flush()
            print(f"Successfully inserted {objects_count} test detected objects.")

        print("Seeding transaction committed successfully.")
    except Exception as e:
        session.rollback()
        print("Error during database seeding, transaction rolled back:", e)
        raise e
    finally:
        session.close()

if __name__ == "__main__":
    seed_database()
