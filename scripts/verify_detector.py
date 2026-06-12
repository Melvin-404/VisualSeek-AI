import os
import sys
import cv2
from pathlib import Path
import torch

# Add paths to python sys path to import router/detectors if needed
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(WORKSPACE_ROOT / "apps" / "api"))

from app.api.v1.routers.cameras import manager, ALLOWED_CLASSES, validate_detection

def main():
    video_path = WORKSPACE_ROOT / "apps" / "web" / "public" / "uploads" / "video-lobby.mp4"
    if not video_path.exists():
        print(f"VERIFICATION FAILED: test video not found at {video_path}")
        sys.exit(1)
        
    print(f"Opening test video: {video_path}")
    cap = cv2.VideoCapture(str(video_path.resolve()))
    if not cap.isOpened():
        print("VERIFICATION FAILED: could not open test video file")
        sys.exit(1)
        
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        print("VERIFICATION FAILED: could not read first frame of test video")
        sys.exit(1)
        
    print("Frame read successfully. Running YOLO track on single frame...")
    
    try:
        # Load weights and run inference directly
        results = manager.model.track(
            source=frame,
            persist=True,
            conf=0.45,
            iou=0.45,
            classes=[0, 1, 2, 3, 5, 7],
            verbose=False,
            half=manager.use_half
        )
    except Exception as e:
        print(f"VERIFICATION FAILED: Inference run crashed: {e}")
        sys.exit(1)
        
    print("\n--- RAW ULTRALYTICS RESULTS OBJECT ---")
    print(results)
    print("--------------------------------------\n")
    
    detections = []
    if results and results[0].boxes is not None:
        boxes = results[0].boxes
        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i].item())
            conf = round(float(boxes.conf[i].item()), 2)
            xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
            track_id = int(boxes.id[i].item()) if boxes.id is not None else None
            
            label = ALLOWED_CLASSES.get(cls_id, f"unknown_{cls_id}")
            print(f"REAL DETECTION: class_id={cls_id} label={label} conf={conf} bbox={list(xyxy)} track_id={track_id}")
            
            det = {
                "track_id": track_id,
                "class_id": cls_id,
                "class_label": label,
                "confidence": conf,
                "bbox": {"x1": int(xyxy[0]), "y1": int(xyxy[1]), "x2": int(xyxy[2]), "y2": int(xyxy[3])},
                "frame_id": 1,
                "timestamp_ms": 0.0,
                "camera_id": "test_cam"
            }
            detections.append(det)

    # Perform assertions
    forbidden_labels = ["vehicle", "laptop", "package", "cell phone", "person (unconfirmed)"]
    allowed_ids = [0, 1, 2, 3, 5, 7]
    
    for det in detections:
        label = det["class_label"]
        cls_id = det["class_id"]
        
        if label in forbidden_labels:
            print(f"VERIFICATION FAILED: Forbidden label '{label}' detected!")
            sys.exit(1)
            
        if cls_id not in allowed_ids:
            print(f"VERIFICATION FAILED: Class ID {cls_id} is not in the allowed list!")
            sys.exit(1)
            
        if not validate_detection(det):
            print(f"VERIFICATION FAILED: Detection object fails schema validation: {det}")
            sys.exit(1)
            
    print("VERIFICATION PASSED")

if __name__ == "__main__":
    main()
