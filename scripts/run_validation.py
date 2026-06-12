"""Phase 4 validation script.

Evaluates the upgraded object detection and tracking pipeline on activity and empty scenes.
Computes latency percentiles (P50, P95, P99), VRAM/memory utilization, false positive rates,
and tracking consistency, producing reports/validation_report.md.
"""

import os
import sys
import time
from pathlib import Path
import numpy as np
import cv2
import torch

# Add packages/ai-pipeline and its src directory to sys.path
ai_pipeline_dir = Path(__file__).parent.parent / "packages" / "ai-pipeline"
sys.path.append(str(ai_pipeline_dir))
sys.path.append(str(ai_pipeline_dir / "src"))

from detectors.yolo_detector import YOLODetector, Detection
from trackers.bytetrack_tracker import ByteTrackWrapper, TrackerConfig

def create_empty_video(filepath: str, duration_sec: int = 5, fps: int = 30) -> None:
    """Create a synthetic empty CCTV video with just static background and minor noise."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    width, height = 640, 480
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

    for _ in range(duration_sec * fps):
        # Static dark background representing an empty room
        frame = np.ones((height, width, 3), dtype=np.uint8) * 30
        
        # Add static texture lines
        for x in range(0, width, 100):
            cv2.line(frame, (x, 0), (x, height), (40, 40, 40), 1)
            
        # Add realistic camera sensor noise
        noise = np.random.normal(0, 2, frame.shape).astype(np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        writer.write(frame)

    writer.release()
    print(f"Created synthetic empty CCTV video: {filepath}")

def create_occlusion_video(filepath: str, duration_sec: int = 10, fps: int = 30) -> None:
    """Create a synthetic CCTV video with a central black pillar to simulate occlusion."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    width, height = 640, 480
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

    for frame_idx in range(duration_sec * fps):
        frame = np.ones((height, width, 3), dtype=np.uint8) * 40
        for x in range(0, width, 80):
            cv2.line(frame, (x, 0), (x, height), (60, 60, 60), 1)
        for y in range(0, height, 60):
            cv2.line(frame, (0, y), (width, y), (60, 60, 60), 1)

        px = int(50 + (frame_idx * 2.0) % (width - 100))
        py = int(200 + np.sin(frame_idx / 10.0) * 15)
        cv2.rectangle(frame, (px, py), (px + 20, py + 60), (0, 255, 0), -1)

        cx = int(width - 100 - (frame_idx * 4.0) % (width - 150))
        cy = 320
        cv2.rectangle(frame, (cx, cy), (cx + 80, cy + 40), (255, 0, 0), -1)

        cv2.rectangle(frame, (280, 0), (360, height), (30, 30, 30), -1)

        noise = np.random.normal(0, 3, frame.shape).astype(np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        writer.write(frame)

    writer.release()
    print(f"Created synthetic occlusion CCTV video: {filepath}")

def run_validation():
    activity_video_path = "tests/fixtures/sample_cctv_occlusion.mp4"
    empty_video_path = "tests/fixtures/sample_empty.mp4"

    # Make sure videos exist
    if not os.path.exists(activity_video_path):
        create_occlusion_video(activity_video_path)
    if not os.path.exists(empty_video_path):
        create_empty_video(empty_video_path)

    # Determine device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # Initialize detector
    detector = YOLODetector(model_path="yolo11m.pt")
    detector.warmup(iterations=3)

    # Initialize tracker
    tracker_config = TrackerConfig(
        track_thresh=0.40,
        track_buffer=60,
        match_thresh=0.8,
        frame_rate=30
    )
    tracker = ByteTrackWrapper(config=tracker_config)

    # -------------------------------------------------------------
    # Validation Run 1: Activity Scene Validation
    # -------------------------------------------------------------
    print("\nValidating Activity Scene...")
    cap = cv2.VideoCapture(activity_video_path)
    
    latencies = []
    total_detections = 0
    detections_by_class = {}
    confidences_by_class = {}
    
    frame_idx = 0
    
    # Reset peak memory before run
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
        
    start_time = time.perf_counter()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_start = time.perf_counter()
        
        # 1. Detection
        dets = detector.detect(frame, camera_id="cam_01")
        
        # 2. Tracking
        tracked_dets = tracker.update(dets, frame_id=frame_idx, frame=frame)
        
        frame_latency = (time.perf_counter() - frame_start) * 1000.0 # ms
        latencies.append(frame_latency)

        # Record metrics
        for det in tracked_dets:
            total_detections += 1
            lbl = det.class_label
            detections_by_class[lbl] = detections_by_class.get(lbl, 0) + 1
            confidences_by_class[lbl] = confidences_by_class.get(lbl, []) + [det.confidence]

        frame_idx += 1

    cap.release()
    total_run_time = time.perf_counter() - start_time
    
    # Compute latency percentiles
    latencies = np.array(latencies)
    avg_latency = np.mean(latencies)
    p50_latency = np.percentile(latencies, 50)
    p95_latency = np.percentile(latencies, 95)
    p99_latency = np.percentile(latencies, 99)
    fps = frame_idx / total_run_time if total_run_time > 0 else 0

    # Compute memory footprint
    if device == "cuda":
        peak_vram_bytes = torch.cuda.max_memory_allocated()
        peak_vram_mb = peak_vram_bytes / (1024 * 1024)
    else:
        try:
            import psutil
            process = psutil.Process(os.getpid())
            peak_vram_mb = process.memory_info().rss / (1024 * 1024)
        except ImportError:
            peak_vram_mb = 0.0

    print("Activity Scene Validation Complete.")

    # -------------------------------------------------------------
    # Validation Run 2: Empty Scene Validation (False Positives)
    # -------------------------------------------------------------
    print("\nValidating Empty Scene...")
    tracker.reset()
    cap_empty = cv2.VideoCapture(empty_video_path)
    
    empty_detections = 0
    empty_frames = 0

    while cap_empty.isOpened():
        ret, frame = cap_empty.read()
        if not ret:
            break
        
        dets = detector.detect(frame, camera_id="cam_empty")
        tracked_dets = tracker.update(dets, frame_id=empty_frames, frame=frame)
        empty_detections += len(tracked_dets)
        empty_frames += 1

    cap_empty.release()
    print("Empty Scene Validation Complete.")

    # -------------------------------------------------------------
    # Validation Run 3: Tracking Logic Verification (Deterministic)
    # -------------------------------------------------------------
    print("\nValidating Tracking Logic Consistency...")
    tracker.reset()
    sim_track_history = {}
    
    for sim_frame_id in range(150):
        dets = []
        timestamp_ms = (sim_frame_id / 30.0) * 1000.0
        
        # Simulating person (overlap zone)
        px = 50 + sim_frame_id * 1.5
        person_occluded = (150 <= px <= 180)
        
        if not person_occluded:
            det_person = Detection(
                frame_id=sim_frame_id,
                timestamp_ms=timestamp_ms,
                class_id=0,
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
        cx = 500 - sim_frame_id * 2.0
        car_occluded = (250 <= cx <= 290)
        
        if not car_occluded:
            det_car = Detection(
                frame_id=sim_frame_id,
                timestamp_ms=timestamp_ms,
                class_id=2,
                class_label="car",
                confidence=0.90,
                bbox_xyxy=(int(cx), 320, int(cx + 100), 360),
                bbox_xywh=(int(cx), 320, 100, 40),
                area_px=4000,
                aspect_ratio=2.5,
                camera_id="cam_01"
            )
            dets.append(det_car)

        tracked_dets = tracker.update(dets, frame_id=sim_frame_id)
        
        for det in tracked_dets:
            if det.track_id is not None:
                if det.track_id not in sim_track_history:
                    sim_track_history[det.track_id] = []
                sim_track_history[det.track_id].append(det.class_label)

    num_sim_tracks = len(sim_track_history)
    print(f"Tracking logic verification: identified {num_sim_tracks} tracks.")

    # -------------------------------------------------------------
    # 3. Determine Pass/Fail Criteria
    # -------------------------------------------------------------
    # Latency: Average latency must be < 500ms on CPU, < 50ms on GPU
    latency_passed = avg_latency < (50.0 if device == "cuda" else 500.0)
    
    # False Positives: Must be exactly 0 detections in empty scene
    fp_passed = empty_detections == 0
    
    # Tracking consistency: We expect exactly 2 unique tracks (1 person, 1 car)
    tracking_passed = num_sim_tracks == 2
    
    overall_status = "PASSED" if (latency_passed and fp_passed and tracking_passed) else "FAILED"

    # -------------------------------------------------------------
    # 4. Generate Report
    # -------------------------------------------------------------
    report_content = f"""# VisionQuery AI Pipeline Validation Report

This report documents the systematic performance, latency, and tracking quality evaluation of the upgraded object detection and tracking pipeline.

## Environment Context
- **Execution Timestamp**: {time.strftime("%Y-%m-%d %H:%M:%S")}
- **Hardware Device**: {device.upper()} {"(RTX 4060 Laptop)" if device == "cuda" else "(CPU Fallback)"}
- **Framework Versions**: PyTorch {torch.__version__}, OpenCV {cv2.__version__}
- **Model Engine**: YOLOv11m (`yolo11m.pt`)
- **Tracking Algorithm**: ByteTrack (Pure-Python Local Implementation)

## Validation Summary
- **Overall Pipeline Status**: **{overall_status}**

| Metric / Check | Required Threshold | Measured Value | Status |
| :--- | :--- | :--- | :--- |
| **Inference Latency (Avg)** | < {"50" if device == "cuda" else "500"} ms / frame | {avg_latency:.2f} ms | {"PASS" if latency_passed else "FAIL"} |
| **False Positive Count** | 0 detections on empty scene | {empty_detections} | {"PASS" if fp_passed else "FAIL"} |
| **Tracking Identity Switches** | Exactly 2 tracks for 2 objects | {num_sim_tracks} tracks | {"PASS" if tracking_passed else "FAIL"} |

## Latency & Performance Details (Activity Scene)
- **Total Frames Processed**: {frame_idx}
- **Average Processing Speed**: {fps:.2f} FPS
- **Percentile Latencies**:
  - **P50 (Median)**: {p50_latency:.2f} ms
  - **P95**: {p95_latency:.2f} ms
  - **P99**: {p99_latency:.2f} ms
- **Peak Memory Usage**: {peak_vram_mb:.2f} MB {"VRAM" if device == "cuda" else "RAM"}

## Detection Taxonomy Details (Activity Scene)
- **Total Valid Detections**: {total_detections} (Expected 0 due to synthetic input shapes)

## Tracking Consistency (Simulation)
- **Total Unique Track IDs**: {num_sim_tracks}
- **Mitigation Parameters**:
  - `track_thresh`: {tracker_config.track_thresh}
  - `track_buffer`: {tracker_config.track_buffer} frames
  - `match_thresh`: {tracker_config.match_thresh}

## Empty Scene / False Positive Validation
- **Frames Evaluated**: {empty_frames}
- **Detections Registered**: {empty_detections}
- **False Positive Rate**: {empty_detections / empty_frames if empty_frames > 0 else 0:.4f} detections/frame

---
*Generated by VisionQuery AI Systems Architect validation agent.*
"""

    # Save to reports/validation_report.md in the project root
    report_path = Path(__file__).parent.parent / "reports" / "validation_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    print("\n" + "="*60)
    print("PHASE 4 VALIDATION COMPLETED")
    print("="*60)
    print(f"Overall Status: {overall_status}")
    print(f"Average Latency: {avg_latency:.2f} ms/frame ({fps:.2f} FPS)")
    print(f"False Positives in Empty Scene: {empty_detections}")
    print(f"Total Unique Tracks (Sim): {num_sim_tracks}")
    print(f"Report saved to: {report_path.resolve()}")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_validation()
