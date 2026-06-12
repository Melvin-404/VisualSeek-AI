"""Phase 2 object detection acceptance test script.

Processes a sample or synthetic CCTV video, runs YOLODetector, and asserts
thresholds, boundaries, and class taxonomy constraints.
"""

import os
import sys
import time
from pathlib import Path
import numpy as np
import cv2

# Add packages/ai-pipeline to path
sys.path.append(str(Path(__file__).parent.parent / "packages" / "ai-pipeline"))

from detectors.yolo_detector import YOLODetector, Detection

def create_synthetic_video(filepath: str, duration_sec: int = 10, fps: int = 30) -> None:
    """Create a synthetic CCTV video with moving shapes representing people and cars."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    width, height = 640, 480
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

    for frame_idx in range(duration_sec * fps):
        # Dark background representing street/lobby
        frame = np.ones((height, width, 3), dtype=np.uint8) * 40
        
        # Draw some grid lines to simulate lanes/tiles
        for x in range(0, width, 80):
            cv2.line(frame, (x, 0), (x, height), (60, 60, 60), 1)
        for y in range(0, height, 60):
            cv2.line(frame, (0, y), (width, y), (60, 60, 60), 1)

        # Draw a moving "person" (vertical rectangle)
        px = int(50 + (frame_idx * 1.5) % (width - 100))
        py = int(200 + np.sin(frame_idx / 10.0) * 30)
        cv2.rectangle(frame, (px, py), (px + 20, py + 60), (0, 255, 0), -1)  # green

        # Draw a moving "car" (horizontal rectangle)
        cx = int(width - 100 - (frame_idx * 3.5) % (width - 150))
        cy = 320
        cv2.rectangle(frame, (cx, cy), (cx + 80, cy + 40), (255, 0, 0), -1)  # blue

        # Add Gaussian-like sensor noise
        noise = np.random.normal(0, 5, frame.shape).astype(np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        writer.write(frame)

    writer.release()
    print(f"Created synthetic CCTV video: {filepath}")

def run_test():
    video_path = "tests/fixtures/sample_cctv.mp4"
    if not os.path.exists(video_path):
        create_synthetic_video(video_path)

    # Initialize YOLODetector
    detector = YOLODetector(model_path="yolo11m.pt")
    detector.warmup(iterations=3)

    cap = cv2.VideoCapture(video_path)
    total_frames = 0
    total_detections = 0
    class_counts = {}
    confidences = {}
    
    start_time = time.perf_counter()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        total_frames += 1
        # Run detector
        dets = detector.detect(frame, camera_id="cam_01")
        
        for det in dets:
            total_detections += 1
            lbl = det.class_label
            
            # Assertions
            assert lbl != "vehicle", "FAIL: Detected 'vehicle' label instead of specific taxonomy class!"
            
            req_conf = detector.config.class_thresholds.get(lbl, detector.config.conf_threshold)
            assert det.confidence >= req_conf, f"FAIL: BBox confidence {det.confidence} is below required threshold {req_conf} for class {lbl}!"
            
            x1, y1, x2, y2 = det.bbox_xyxy
            assert x1 >= 0 and y1 >= 0 and x2 <= frame.shape[1] and y2 <= frame.shape[0], \
                f"FAIL: BBox coordinates ({x1}, {y1}, {x2}, {y2}) are outside frame dimensions {frame.shape[:2]}!"

            class_counts[lbl] = class_counts.get(lbl, 0) + 1
            confidences[lbl] = confidences.get(lbl, []) + [det.confidence]

    cap.release()
    elapsed = time.perf_counter() - start_time
    mean_fps = total_frames / elapsed if elapsed > 0 else 0

    print("\n" + "="*50)
    print("PHASE 2 DETECTION PIPELINE TEST PASSED SUCCESSFULLY")
    print("="*50)
    print(f"Total frames processed: {total_frames}")
    print(f"Total detections: {total_detections}")
    print(f"Average processing speed: {mean_fps:.2f} FPS ({elapsed*1000/total_frames:.2f} ms/frame)")
    print("Detections per class:")
    for cls, count in class_counts.items():
        mean_conf = np.mean(confidences[cls])
        print(f"  - {cls}: {count} (mean confidence: {mean_conf:.4f})")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_test()
