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
sys.path.append(str(root / "packages" / "ai-pipeline" / "detectors"))

# Load env vars
load_dotenv(root / "apps" / "api" / ".env")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.schema_models import DetectedObject, VideoSegment, Camera

# Import extractors
from colour_extractor import DominantColourExtractor
from vehicle_attribute_classifier import VehicleAttributeClassifier
from person_attribute_extractor import PersonAttributeExtractor

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "suv", "van"}

def backfill():
    print("Connecting to database at:", settings.DATABASE_URL)
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Initialize extractors
    print("Loading AI models...")
    colour_extractor = DominantColourExtractor()
    vehicle_classifier = VehicleAttributeClassifier(use_gpu=True)
    person_extractor = PersonAttributeExtractor()
    print("AI models loaded successfully.")

    # Query un-backfilled detected objects
    objects = session.query(DetectedObject).filter(DetectedObject.attributes_extracted == False).all()
    print(f"Found {len(objects)} detected objects to process.")

    cap_cache = {}
    success_count = 0

    try:
        for idx, obj in enumerate(objects):
            print(f"[{idx+1}/{len(objects)}] Processing object ID: {obj.id} ({obj.class_label})")
            
            # Find video segment
            segment = session.query(VideoSegment).filter(VideoSegment.id == obj.segment_id).first()
            if not segment:
                print(f"  Warning: VideoSegment {obj.segment_id} not found in database. Skipping.")
                continue

            # Find Camera to map to local video file
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

            # Extract crop Bounding Box
            h_img, w_img = frame.shape[:2]
            x1 = int(obj.bbox_x * w_img)
            y1 = int(obj.bbox_y * h_img)
            w = int(obj.bbox_w * w_img)
            h = int(obj.bbox_h * h_img)

            # Keep coordinates inside frame
            x1 = max(0, min(x1, w_img - 1))
            y1 = max(0, min(y1, h_img - 1))
            x2 = max(0, min(x1 + w, w_img))
            y2 = max(0, min(y1 + h, h_img))

            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                print(f"  Warning: Empty crop extracted for bbox: [{x1}, {y1}, {x2}, {y2}]. Skipping.")
                continue

            # 1. Dominant colour extraction (for all classes)
            color_res = colour_extractor.extract(crop)
            obj.dominant_colour = color_res["dominant_colour"]
            obj.colour_confidence = color_res["colour_confidence"]
            print(f"  Extracted dominant colour: {obj.dominant_colour} (conf: {obj.colour_confidence})")

            # 2. Vehicle attribute classification
            if obj.class_label.lower() in VEHICLE_CLASSES:
                veh_res = vehicle_classifier.classify_batch([crop])[0]
                obj.vehicle_type = veh_res["vehicle_type"]
                obj.vehicle_type_confidence = veh_res["vehicle_type_confidence"]
                print(f"  Extracted vehicle style: {obj.vehicle_type} (conf: {obj.vehicle_type_confidence})")

            # 3. Person attribute extraction
            elif obj.class_label.lower() == "person":
                pers_res = person_extractor.extract(crop)
                obj.upper_colour = pers_res["upper_colour"]
                obj.upper_colour_conf = pers_res["upper_colour_conf"]
                obj.lower_colour = pers_res["lower_colour"]
                obj.lower_colour_conf = pers_res["lower_colour_conf"]
                obj.carried_items = pers_res["carried_items"]
                obj.gender_estimate = pers_res["gender_estimate"]
                obj.gender_is_estimate = pers_res["gender_is_estimate"]
                print(f"  Extracted person attributes: upper={obj.upper_colour}, lower={obj.lower_colour}, carried={obj.carried_items}, gender={obj.gender_estimate}")

            obj.attributes_extracted = True
            success_count += 1

        # Commit all updates
        print("Committing transaction...")
        session.commit()
        print(f"Successfully backfilled attributes for {success_count}/{len(objects)} detected objects.")
    except Exception as e:
        session.rollback()
        print("Error during backfill, transaction rolled back:", e)
        raise e
    finally:
        session.close()
        for cap in cap_cache.values():
            cap.release()

if __name__ == "__main__":
    backfill()
