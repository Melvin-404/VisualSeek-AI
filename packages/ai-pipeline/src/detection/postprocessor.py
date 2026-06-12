"""Postprocessing, NMS, and taxonomy mapping for YOLOv10 detections."""

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from detection.config import DetectionConfig

# Define the custom 64-class surveillance taxonomy.
# The first 64 map roughly to standard COCO classes for seamless YOLO mapping.
SURVEILLANCE_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "street sign", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
    "hat", "backpack", "umbrella", "shoe", "eye glasses", "handbag", "tie", "suitcase",
    "frisbee", "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "plate", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli",
    "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant"
]

VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "bicycle", "train", "boat", "airplane"}


@dataclass(frozen=True)
class DetectionResult:
    """Dataclass holding detection box, category, confidence, and metadata."""

    box: Tuple[float, float, float, float]  # [x1, y1, x2, y2]
    class_id: int
    class_name: str
    confidence: float
    metadata: dict


class Postprocessor:
    """Handles class thresholding, NMS, and inverse letterboxing for YOLOv10."""

    def __init__(self, config: DetectionConfig):
        """Initialize postprocessor with configuration."""
        self.config = config

    def _get_threshold_for_class(self, class_name: str) -> float:
        """Get confidence threshold for a class based on category mappings."""
        thresholds = self.config.confidence_thresholds
        if class_name == "person":
            return thresholds.get("person", 0.4)
        elif class_name in VEHICLE_CLASSES:
            return thresholds.get("vehicle", 0.5)
        else:
            return thresholds.get("object", 0.3)

    def _restore_letterbox(
        self, box: np.ndarray, original_dim: Tuple[int, int], target_dim: Tuple[int, int] = (640, 640)
    ) -> Tuple[float, float, float, float]:
        """Restore coordinates from letterboxed frame back to original image size.

        Args:
            box: Bounding box coordinates [x1, y1, x2, y2] in target_dim.
            original_dim: Original image size as (width, height).
            target_dim: Letterboxed target size as (width, height).

        Returns:
            Tuple of [x1, y1, x2, y2] in original image space.
        """
        w, h = original_dim
        tw, th = target_dim

        # Calculate scale and padding used in pytorch_letterbox
        scale = min(tw / w, th / h)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))

        left = (tw - new_w) // 2
        top = (th - new_h) // 2

        # Extract coordinates
        x1, y1, x2, y2 = box

        # Unpad and scale
        x1_orig = (x1 - left) / scale
        y1_orig = (y1 - top) / scale
        x2_orig = (x2 - left) / scale
        y2_orig = (y2 - top) / scale

        # Clamp to image boundaries
        x1_orig = max(0.0, min(float(x1_orig), float(w)))
        y1_orig = max(0.0, min(float(y1_orig), float(h)))
        x2_orig = max(0.0, min(float(x2_orig), float(w)))
        y2_orig = max(0.0, min(float(y2_orig), float(h)))

        return (x1_orig, y1_orig, x2_orig, y2_orig)

    def _nms(self, boxes: np.ndarray, scores: np.ndarray, class_ids: np.ndarray) -> List[int]:
        """Perform batched class-specific Non-Maximum Suppression (NMS)."""
        if len(boxes) == 0:
            return []

        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]

        areas = (x2 - x1) * (y2 - y1)
        
        # Apply class offset to separate classes in coordinates space
        # (prevents boxes of different classes from suppressing each other)
        offsets = class_ids.astype(np.float32) * 10000.0
        x1_offset = x1 + offsets
        y1_offset = y1 + offsets
        x2_offset = x2 + offsets
        y2_offset = y2 + offsets

        order = scores.argsort()[::-1]
        keep = []

        while order.size > 0:
            i = order[0]
            keep.append(int(i))

            xx1 = np.maximum(x1_offset[i], x1_offset[order[1:]])
            yy1 = np.maximum(y1_offset[i], y1_offset[order[1:]])
            xx2 = np.minimum(x2_offset[i], x2_offset[order[1:]])
            yy2 = np.minimum(y2_offset[i], y2_offset[order[1:]])

            w = np.maximum(0.0, xx2 - xx1)
            h = np.maximum(0.0, yy2 - yy1)
            inter = w * h

            ovr = inter / (areas[i] + areas[order[1:]] - inter)

            inds = np.where(ovr <= self.config.iou_threshold)[0]
            order = order[inds + 1]

        return keep

    def postprocess(
        self, raw_outputs: np.ndarray, original_dims: List[Tuple[int, int]]
    ) -> List[List[DetectionResult]]:
        """Filter raw engine predictions, restore coords, map taxonomy, and run NMS.

        Args:
            raw_outputs: Raw predictions from inference engine of shape (B, 300, 6)
                         where each detection is [x1, y1, x2, y2, score, class_id].
            original_dims: List of original image dimensions (width, height) for each batch element.

        Returns:
            List of lists containing DetectionResult objects (one list per batch element).
        """
        batch_size = raw_outputs.shape[0]
        assert batch_size == len(original_dims), "Batch size mismatch with original dimensions list."

        batch_results: List[List[DetectionResult]] = []

        for b in range(batch_size):
            detections = raw_outputs[b]  # shape (300, 6)
            orig_dim = original_dims[b]

            # 1. Filter out low confidence detections and invalid class indices
            valid_boxes = []
            valid_scores = []
            valid_class_ids = []
            valid_class_names = []

            for det in detections:
                # Bounding box coordinates, score, class
                x1, y1, x2, y2, score, class_id_f = det
                class_id = int(class_id_f)

                # Skip padded/dummy detections in YOLO output (often zero score or negative class)
                if score <= 0.0 or class_id < 0:
                    continue

                # Map class ID to custom surveillance taxonomy
                if class_id < len(SURVEILLANCE_CLASSES):
                    class_name = SURVEILLANCE_CLASSES[class_id]
                else:
                    class_name = "object"

                # Check class-specific threshold
                threshold = self._get_threshold_for_class(class_name)
                if score >= threshold:
                    valid_boxes.append([x1, y1, x2, y2])
                    valid_scores.append(score)
                    valid_class_ids.append(class_id)
                    valid_class_names.append(class_name)

            if len(valid_boxes) == 0:
                batch_results.append([])
                continue

            valid_boxes_arr = np.array(valid_boxes, dtype=np.float32)
            valid_scores_arr = np.array(valid_scores, dtype=np.float32)
            valid_class_ids_arr = np.array(valid_class_ids, dtype=np.int32)

            # 2. Run NMS
            keep_indices = self._nms(valid_boxes_arr, valid_scores_arr, valid_class_ids_arr)

            # 3. Restore letterboxed boxes to original scale and build DetectionResult objects
            results = []
            for idx in keep_indices:
                box_restored = self._restore_letterbox(valid_boxes_arr[idx], orig_dim)
                results.append(
                    DetectionResult(
                        box=box_restored,
                        class_id=int(valid_class_ids_arr[idx]),
                        class_name=valid_class_names[idx],
                        confidence=float(valid_scores_arr[idx]),
                        metadata={},
                    )
                )

            batch_results.append(results)

        return batch_results
