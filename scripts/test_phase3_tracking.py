"""Phase 3 multi-object tracking acceptance test script.

Runs YOLODetector to ensure compatibility, then runs a deterministic tracking
simulation with simulated detections to validate ByteTrack track ID assignment,
ID confirmation, and occlusion recovery.
"""

import os
import sys
import time
from pathlib import Path
import numpy as np
import cv2

# Add packages/ai-pipeline and its src directory to sys.path
ai_pipeline_dir = Path(__file__).parent.parent / "packages" / "ai-pipeline"
sys.path.append(str(ai_pipeline_dir))
sys.path.append(str(ai_pipeline_dir / "src"))

from detectors.yolo_detector import YOLODetector, Detection
from trackers.bytetrack_tracker import ByteTrackWrapper, TrackerConfig

def run_test():
    # -------------------------------------------------------------
    # 1. Compatibility Check: Run YOLODetector & ByteTrackWrapper on video
    # -------------------------------------------------------------
    print("Running detector & tracker integration compatibility check...")
    video_path = "tests/fixtures/sample_cctv.mp4"
    if not os.path.exists(video_path):
        # Create a tiny dummy video if not exists
        width, height = 640, 480
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(video_path, fourcc, 30, (width, height))
        for _ in range(30):
            frame = np.ones((height, width, 3), dtype=np.uint8) * 40
            writer.write(frame)
        writer.release()

    detector = YOLODetector(model_path="yolo11m.pt")
    detector.warmup(iterations=1)

    tracker_config = TrackerConfig(
        track_thresh=0.40,
        track_buffer=60,
        match_thresh=0.8,
        frame_rate=30
    )
    tracker = ByteTrackWrapper(config=tracker_config)

    cap = cv2.VideoCapture(video_path)
    frames_processed = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        dets = detector.detect(frame, camera_id="cam_01")
        _ = tracker.update(dets, frame_id=frames_processed, frame=frame)
        frames_processed += 1
    cap.release()
    print(f"Integration compatibility check passed. Processed {frames_processed} frames successfully.")

    # -------------------------------------------------------------
    # 2. Deterministic Tracking Simulation (Occlusion & ID recovery)
    # -------------------------------------------------------------
    print("\nRunning deterministic tracking simulation...")
    tracker.reset()
    
    # Track history: track_id -> list of frame_ids
    track_history = {}
    
    # We will simulate 150 frames
    # Person starts at x=50, moves by +1.5 pixels/frame, width=50
    # Car starts at x=500, moves by -2.0 pixels/frame, width=100
    
    for frame_id in range(150):
        dets = []
        timestamp_ms = (frame_id / 30.0) * 1000.0
        
        # Simulating person
        px = 50 + frame_id * 1.5
        # Person is occluded when px is between 150 and 180 (frames 67 to 86)
        person_occluded = (150 <= px <= 180)
        
        if not person_occluded:
            det_person = Detection(
                frame_id=frame_id,
                timestamp_ms=timestamp_ms,
                class_id=0, # person
                class_label="person",
                confidence=0.85,
                bbox_xyxy=(int(px), 200, int(px + 50), 260),
                bbox_xywh=(int(px), 200, 50, 60),
                area_px=3000,
                aspect_ratio=0.83,
                camera_id="cam_01"
            )
            dets.append(det_person)

        # Simulating car
        cx = 500 - frame_id * 2.0
        # Car is occluded when cx is between 250 and 290 (frames 105 to 125)
        car_occluded = (250 <= cx <= 290)
        
        if not car_occluded:
            det_car = Detection(
                frame_id=frame_id,
                timestamp_ms=timestamp_ms,
                class_id=2, # car
                class_label="car",
                confidence=0.90,
                bbox_xyxy=(int(cx), 320, int(cx + 100), 360),
                bbox_xywh=(int(cx), 320, 100, 40),
                area_px=4000,
                aspect_ratio=2.5,
                camera_id="cam_01"
            )
            dets.append(det_car)

        # Update tracker
        tracked_dets = tracker.update(dets, frame_id=frame_id)
        
        for det in tracked_dets:
            if det.track_id is not None:
                if det.track_id not in track_history:
                    track_history[det.track_id] = []
                track_history[det.track_id].append((frame_id, det.class_label))

    print("\n" + "="*60)
    print("PHASE 3 TRACKING SIMULATION RESULTS")
    print("="*60)
    print(f"Total unique tracks identified: {len(track_history)}")
    
    person_track_ids = []
    car_track_ids = []
    
    for tid, history in sorted(track_history.items()):
        frames = [h[0] for h in history]
        label = history[0][1]
        print(f"  - Track ID {tid:02d} [{label}]: frames {min(frames)}-{max(frames)} ({len(frames)} active frames)")
        if label == "person":
            person_track_ids.append(tid)
        elif label == "car":
            car_track_ids.append(tid)

    # -------------------------------------------------------------
    # 3. Assertions
    # -------------------------------------------------------------
    # We expect exactly 1 track ID for the person and 1 track ID for the car
    # because ByteTrack should recover the track IDs after the occlusion zones!
    assert len(person_track_ids) == 1, f"FAIL: Expected exactly 1 track ID for person, got {person_track_ids}!"
    assert len(car_track_ids) == 1, f"FAIL: Expected exactly 1 track ID for car, got {car_track_ids}!"
    
    print("\nSUCCESS: All tracking assertions passed! Occlusion recovery succeeded.")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_test()
