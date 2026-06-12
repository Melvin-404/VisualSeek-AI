# =========================================================================================
# VERIFICATION RUN FOR REAL-TIME DETECTION PIPELINE
# =========================================================================================
# Opening test video: C:\Users\Mohommed Adil\Desktop\Vision Query\apps\web\public\uploads\video-lobby.mp4
# Frame read successfully. Running YOLO track on single frame...
#
# --- RAW ULTRALYTICS RESULTS OBJECT ---
# names: {0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane', 5: 'bus', 6: 'train', 7: 'truck', ...}
# orig_shape: (720, 1280)
#
# REAL DETECTION: class_id=7 label=truck conf=0.89 bbox=[959, 415, 1279, 716] track_id=1
# REAL DETECTION: class_id=7 label=truck conf=0.88 bbox=[0, 247, 166, 410] track_id=2
# REAL DETECTION: class_id=2 label=car conf=0.75 bbox=[536, 113, 586, 155] track_id=3
# REAL DETECTION: class_id=0 label=person conf=0.61 bbox=[136, 356, 183, 427] track_id=4
# REAL DETECTION: class_id=7 label=truck conf=0.6 bbox=[216, 218, 305, 289] track_id=5
# REAL DETECTION: class_id=2 label=car conf=0.59 bbox=[337, 63, 370, 95] track_id=6
# REAL DETECTION: class_id=3 label=motorcycle conf=0.54 bbox=[134, 390, 194, 447] track_id=7
# REAL DETECTION: class_id=7 label=truck conf=0.5 bbox=[198, 99, 252, 157] track_id=8
# REAL DETECTION: class_id=2 label=car conf=0.5 bbox=[558, 44, 587, 69] track_id=9
# REAL DETECTION: class_id=2 label=car conf=0.46 bbox=[216, 218, 304, 289] track_id=10
#
# VERIFICATION PASSED
# =========================================================================================

"""YOLOv11m object detector and image preprocessing pipeline.

This module implements the YOLODetector class utilizing ultralytics YOLOv11m
to detect persons and vehicles in CCTV camera feeds. It includes custom configuration
options for confidence thresholds, bounding box area, and aspect ratio filters.
"""

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple, Dict
import numpy as np
import torch
from ultralytics import YOLO

# Set up module-level logger
logger = logging.getLogger(__name__)

# COCO Target Class Mapping: Class ID -> Label
COCO_TARGET_CLASSES: Dict[int, str] = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

@dataclass
class Detection:
    """Dataclass holding standard formatted detection attributes for VisionQuery."""
    frame_id: int
    timestamp_ms: float
    class_id: int
    class_label: str
    confidence: float
    bbox_xyxy: Tuple[int, int, int, int]
    bbox_xywh: Tuple[int, int, int, int]
    area_px: int
    aspect_ratio: float
    camera_id: str
    track_id: Optional[int] = None
    crop: Optional[np.ndarray] = None
    crop_path: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize detection attributes to a standard schema dictionary."""
        return {
            "frame_id": self.frame_id,
            "timestamp_ms": self.timestamp_ms,
            "camera_id": self.camera_id,
            "track_id": self.track_id,
            "class_id": self.class_id,
            "class_label": self.class_label,
            "confidence": self.confidence,
            "bbox_xyxy": list(self.bbox_xyxy),
            "bbox_xywh": list(self.bbox_xywh),
            "area_px": self.area_px,
            "aspect_ratio": self.aspect_ratio,
            "crop_path": self.crop_path,
            "frame_embedding": None,
            "object_embedding": None,
            "embedding_model": None,
            "embedding_generated_at": None
        }

@dataclass
class DetectorConfig:
    """Configuration settings for YOLODetector filters and thresholds."""
    conf_threshold: float = 0.45
    iou_threshold: float = 0.45
    class_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "bicycle": 0.50,
        "motorcycle": 0.50,
        "person": 0.42
    })
    min_area: float = 400.0
    max_area_ratio: float = 0.60
    min_aspect_ratio: float = 0.15
    max_aspect_ratio: float = 6.5

class YOLODetector:
    """YOLOv11m object detector wrapping Ultralytics and applying CCTV spatial filters."""

    def __init__(
        self,
        model_path: str = "yolo11m.pt",
        device: Optional[str] = None,
        conf_threshold: float = 0.45,
        iou_threshold: float = 0.45,
        target_classes: Optional[List[int]] = None,
        config: Optional[DetectorConfig] = None
    ):
        """Initialize the YOLOv11m detector.

        Args:
            model_path: Filename/path to the pretrained YOLO model weights.
            device: Target device string (e.g. 'cuda:0', 'cpu'). Auto-selected if None.
            conf_threshold: Global confidence threshold fallback.
            iou_threshold: NMS IoU threshold.
            target_classes: List of COCO class IDs to keep. Defaults to COCO_TARGET_CLASSES keys.
            config: Optional custom DetectorConfig instance.
        """
        # Determine device
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        # Check for force fp32 override
        force_fp32 = os.getenv("FORCE_FP32", "0") == "1"
        self.use_half = (self.device.startswith("cuda") or self.device == "cuda") and not force_fp32

        # Configure thresholds
        self.config = config if config is not None else DetectorConfig(
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold
        )
        self.target_classes = target_classes if target_classes is not None else list(COCO_TARGET_CLASSES.keys())

        # Load Ultralytics model
        logger.info("Loading YOLO model: %s on device: %s", model_path, self.device)
        self.model = YOLO(model_path)
        self.model.to(self.device)

        logger.info(
            "YOLODetector initialised — device=%s, precision=%s, model=%s",
            self.device,
            "fp16" if self.use_half else "fp32",
            model_path
        )

        self._frame_counter = 0

    def warmup(self, iterations: int = 3) -> None:
        """Warm up the GPU/model with dummy forward passes.

        Args:
            iterations: Number of dummy inference runs.
        """
        logger.info("Warming up YOLODetector for %d iterations...", iterations)
        dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
        for _ in range(iterations):
            _ = self.model(dummy_frame, verbose=False, imgsz=640, half=self.use_half, device=self.device)
        logger.info("Warm-up complete.")

    def detect(self, frame: np.ndarray, camera_id: str = "default", export_crops: bool = False) -> List[Detection]:
        """Perform object detection on a frame and apply threshold filters.

        Args:
            frame: Input frame image as a numpy array (BGR format).
            camera_id: Identifier string for the camera stream.
            export_crops: If True, crops the bounding box image regions and populates the crop field.

        Returns:
            List of filtered Detection objects.
        """
        frame_height, frame_width = frame.shape[:2]
        self._frame_counter += 1
        frame_id = self._frame_counter - 1

        # Assume 30fps default for deriving timestamp if not managed externally
        timestamp_ms = (frame_id / 30.0) * 1000.0

        # Run inference using Ultralytics (internal letterboxing enabled by default via imgsz)
        results = self.model(
            frame,
            imgsz=640,
            conf=min(self.config.conf_threshold, min(self.config.class_thresholds.values())),
            iou=self.config.iou_threshold,
            classes=self.target_classes,
            device=self.device,
            half=self.use_half,
            verbose=False
        )

        detections: List[Detection] = []
        if not results:
            return detections

        boxes = results[0].boxes
        if boxes is None:
            return detections

        for box in boxes:
            # Extract coordinates, confidence, class ID
            xyxy = box.xyxy[0].cpu().numpy()
            conf = float(box.conf[0].cpu().numpy())
            cls_id = int(box.cls[0].cpu().numpy())

            # Map COCO ID to label
            if cls_id not in COCO_TARGET_CLASSES:
                logger.debug("Discarding unmapped class ID: %d with confidence: %.4f", cls_id, conf)
                continue
            cls_label = COCO_TARGET_CLASSES[cls_id]

            # 1. Class-specific confidence threshold override check
            req_conf = self.config.class_thresholds.get(cls_label, self.config.conf_threshold)
            if conf < req_conf:
                continue

            # 2. Coordinate clamping to frame dimensions
            x1 = max(0, int(round(xyxy[0])))
            y1 = max(0, int(round(xyxy[1])))
            x2 = min(frame_width, int(round(xyxy[2])))
            y2 = min(frame_height, int(round(xyxy[3])))

            # Derive width, height and area
            w = x2 - x1
            h = y2 - y1
            area = w * h

            # 3. Minimum & Maximum box area filters
            if area < self.config.min_area:
                continue
            max_area = self.config.max_area_ratio * (frame_width * frame_height)
            if area > max_area:
                continue

            # 4. Aspect ratio filters
            if h == 0 or w == 0:
                continue
            aspect_ratio = round(w / h, 3)
            if aspect_ratio < self.config.min_aspect_ratio or aspect_ratio > self.config.max_aspect_ratio:
                continue

            # Crop if requested
            crop_img = None
            if export_crops:
                crop_img = frame[y1:y2, x1:x2].copy()

            # Construct Detection object
            det = Detection(
                frame_id=frame_id,
                timestamp_ms=timestamp_ms,
                class_id=cls_id,
                class_label=cls_label,
                confidence=round(conf, 4),
                bbox_xyxy=(x1, y1, x2, y2),
                bbox_xywh=(x1, y1, w, h),
                area_px=area,
                aspect_ratio=aspect_ratio,
                camera_id=camera_id,
                crop=crop_img
            )
            detections.append(det)

        return detections

    def export_crops(self, frame: np.ndarray, detections: List[Detection], output_dir: str) -> List[Detection]:
        """Extract bounding box crops with 10px padding, save to disk, and record paths.

        Args:
            frame: Input frame image as a numpy array.
            detections: List of Detection objects to export.
            output_dir: Root directory path where crops will be saved.

        Returns:
            List of updated Detection objects with populated crop_path fields.
        """
        import cv2
        frame_h, frame_w = frame.shape[:2]
        
        for det in detections:
            x1, y1, x2, y2 = det.bbox_xyxy
            
            # Apply 10px symmetric padding, clamped to frame dimensions
            px1 = max(0, x1 - 10)
            py1 = max(0, y1 - 10)
            px2 = min(frame_w, x2 + 10)
            py2 = min(frame_h, y2 + 10)
            
            crop_img = frame[py1:py2, px1:px2]
            if crop_img.size == 0:
                continue
                
            # Define output filepath structure
            track_folder = "untracked" if det.track_id is None else f"track_{det.track_id}"
            save_folder = Path(output_dir) / det.camera_id / track_folder
            save_folder.mkdir(parents=True, exist_ok=True)
            
            filename = f"{det.frame_id}_{det.class_label}_{det.confidence:.2f}.jpg"
            filepath = save_folder / filename
            
            # Save JPEG with quality 95
            cv2.imwrite(str(filepath), crop_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            # Populate crop_path with absolute path
            det.crop_path = str(filepath.resolve())
            
        return detections
