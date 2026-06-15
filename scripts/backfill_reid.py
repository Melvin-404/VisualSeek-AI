import os
import sys
import cv2
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

# Add paths to sys.path
root = Path(__file__).resolve().parents[1]
sys.path.append(str(root / "apps" / "api"))
sys.path.append(str(root / "packages" / "ai-pipeline"))
sys.path.append(str(root / "packages" / "ai-pipeline" / "src"))
sys.path.append(str(root / "packages" / "ai-pipeline" / "src" / "tracking"))

# Load env vars
load_dotenv(root / "apps" / "api" / ".env")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.schema_models import DetectedObject, VideoSegment, Camera

# Import ReID and matching models
from reid_model import OSNetReID
from embeddings.clip_encoder import CLIPEncoder
from gallery_matcher import GalleryMatcher

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "suv", "van"}

def backfill_reid():
    print("Connecting to database at:", settings.DATABASE_URL)
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Initialize ReID extractors
    print("Loading ReID and CLIP models...")
    reid_model = OSNetReID(use_gpu=True)
    clip_encoder = CLIPEncoder(model_name="ViT-B-32")
    gallery_matcher = GalleryMatcher()
    print("Models loaded successfully.")

    # Query all detected objects
    objects = session.query(DetectedObject).all()
    print(f"Found {len(objects)} detected objects to process.")

    cap_cache = {}
    matched_count = 0
    created_count = 0

    try:
        for idx, obj in enumerate(objects):
            class_label = obj.class_label.lower()
            is_person = class_label == "person"
            is_vehicle = class_label in VEHICLE_CLASSES

            if not is_person and not is_vehicle:
                # ReID is only performed on persons and vehicles
                continue

            print(f"[{idx+1}/{len(objects)}] Processing ReID for object ID: {obj.id} ({obj.class_label})")

            # Find video segment
            segment = session.query(VideoSegment).filter(VideoSegment.id == obj.segment_id).first()
            if not segment:
                print(f"  Warning: VideoSegment {obj.segment_id} not found in database. Skipping.")
                continue

            # Find Camera
            camera = session.query(Camera).filter(Camera.id == segment.camera_id).first()
            camera_name = camera.name.lower() if camera else ""
            camera_loc = camera.location.lower() if camera else ""

            if "parking" in camera_name or "parking" in camera_loc:
                video_name = "video-parking.mp4"
            else:
                video_name = "video-lobby.mp4"

            video_path = root / "apps" / "web" / "public" / "uploads" / video_name
            if not video_path.exists():
                print(f"  Warning: Local video file {video_path} does not exist. Skipping.")
                continue

            # Open or get from cache
            if video_name not in cap_cache:
                cap = cv2.VideoCapture(str(video_path))
                if cap.isOpened():
                    cap_cache[video_name] = cap
                else:
                    print(f"  Warning: Could not open VideoCapture for {video_path}. Skipping.")
                    continue
            cap = cap_cache[video_name]

            # Seek frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, obj.frame_number)
            ret, frame = cap.read()
            if not ret:
                print(f"  Warning: Could not read frame {obj.frame_number} from {video_name}. Skipping.")
                continue

            # Crop dimensions
            h_img, w_img = frame.shape[:2]
            x1 = int(obj.bbox_x * w_img)
            y1 = int(obj.bbox_y * h_img)
            w = int(obj.bbox_w * w_img)
            h = int(obj.bbox_h * h_img)

            x1 = max(0, min(x1, w_img - 1))
            y1 = max(0, min(y1, h_img - 1))
            x2 = max(0, min(x1 + w, w_img))
            y2 = max(0, min(y1 + h, h_img))

            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                print(f"  Warning: Empty crop for bbox. Skipping.")
                continue

            embedding = None

            if is_person:
                # Person ReID (OSNet-AIN / ResNet-18)
                # BBoxes input to extract_embeddings is [x1, y1, x2, y2]
                bbox_pixel = (float(x1), float(y1), float(x2), float(y2))
                embeddings = reid_model.extract_embeddings(frame, [bbox_pixel])
                if len(embeddings) > 0:
                    embedding = embeddings[0]

            elif is_vehicle:
                # Vehicle ReID (CLIP image embedding)
                crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                emb_batch, _, _ = clip_encoder.encode_image([crop_rgb])
                if len(emb_batch) > 0:
                    embedding = emb_batch[0]

            if embedding is not None:
                # L2 normalize
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm

                # Store embedding
                obj.reid_embedding = embedding.tolist()

                # Gallery match and update
                gallery_id = gallery_matcher.match_and_update(session, obj, embedding)
                if gallery_id:
                    # Let's count whether we matched or created
                    # (since match_and_update assigns it to obj.gallery_id, let's look at the database check)
                    print(f"  Gallery matched/profile created for {obj.class_label}. Gallery ID: {gallery_id}")

        print("Committing transaction...")
        session.commit()
        
        # Print gallery summaries
        from app.models.schema_models import IdentityGallery
        total_identities = session.query(IdentityGallery).count()
        person_identities = session.query(IdentityGallery).filter(IdentityGallery.object_type == "person").count()
        vehicle_identities = session.query(IdentityGallery).filter(IdentityGallery.object_type == "vehicle").count()
        print(f"ReID Backfill Complete. Total gallery profiles created: {total_identities} (Persons: {person_identities}, Vehicles: {vehicle_identities})")

    except Exception as e:
        session.rollback()
        print("Error during ReID backfill, transaction rolled back:", e)
        raise e
    finally:
        session.close()
        for cap in cap_cache.values():
            cap.release()

if __name__ == "__main__":
    backfill_reid()
