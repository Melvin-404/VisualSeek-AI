# VisionQuery AI Detection Pipeline Audit Report

## 1. Executive Summary
The VisionQuery AI detection pipeline currently utilizes a YOLOv10-based architecture implemented via local TensorRT execution with ONNX Runtime and Ultralytics CPU fallbacks. While the pipeline is functional and robust against environment variations (due to the thread-safe ModelRegistry and fallback wrappers), it exhibits minor false positive risks due to low confidence thresholds (e.g., `person: 0.4` and `object: 0.3`) and a complete lack of geometric size/aspect-ratio filtering on predictions. Additionally, batched class-specific NMS prevents overlapping bounding boxes from different classes from suppressing each other, which can lead to duplicate detections of the same physical object. Upgrading to YOLOv11m and implementing rigorous spatial and temporal filters will significantly enhance precision for critical CCTV classes.

## 2. Current Model Inventory
| Module Name | Model Architecture | Weight File Path | Input Resolution | Device Type | Precision | Inference Backend |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `YOLOTensorRTEngine` | YOLOv10x | `models/yolov10x.onnx` / `.engine` | 640×640 | GPU (CPU Fallback) | INT8 / FP16 | TensorRT (fallback: ONNX Runtime / Ultralytics) |

## 3. Threshold Configuration
| Class | Confidence Threshold | NMS IoU Threshold | Source |
| :--- | :--- | :--- | :--- |
| `person` | 0.40 | 0.45 | Config (`DetectionConfig`) |
| `vehicle` | 0.50 | 0.45 | Config (`DetectionConfig`) |
| `object` | 0.30 | 0.45 | Config (`DetectionConfig`) |

## 4. Class Mapping Analysis
The model outputs standard COCO classes which map to a custom 64-class taxonomy (`SURVEILLANCE_CLASSES`). Detections are filtered at the postprocessing step.

| Model Class ID | Model Label | Displayed Label | Suppressed? |
| :---: | :--- | :--- | :---: |
| 0 | person | person | N |
| 1 | bicycle | bicycle | N |
| 2 | car | car | N |
| 3 | motorcycle | motorcycle | N |
| 5 | bus | bus | N |
| 7 | truck | truck | N |
| Other | Various | object | N |

## 5. False Positive Root Causes
1. **Low Confidence Thresholds (Issue FP-001 - Severity: Medium)**: Confidence thresholds for `person` (0.40) and generic `object` (0.30) are relatively low, permitting low-confidence predictions and noise to pass into the event detection layer.
2. **Missing Box Area Constraints (Issue FP-002 - Severity: High)**: Distance noise and background artifacts are not filtered, as there is no minimum bounding box size threshold (e.g., rejecting boxes < 400 px²).
3. **Missing Aspect Ratio Validation (Issue FP-003 - Severity: High)**: Occluded objects or detector errors can output highly stretched boxes (extremely wide or tall), which are currently accepted without validation.
4. **No Cross-Class NMS (Issue FP-004 - Severity: Medium)**: Multi-class overlapping boxes for the same object (e.g., overlapping car and truck detections) are not merged or resolved.
5. **No Temporal Consistency (Issue FP-005 - Severity: Medium)**: Single-frame detections are accepted immediately without verification that the track continues for a minimum number of frames, leading to momentary flickers appearing as events.

## 6. Recommended Actions
1. **Upgrade Detector to YOLOv11m**: Replace YOLOv10x with a cleaner PyTorch-native YOLOv11m interface to improve baseline accuracy and simplify device deployment.
2. **Implement Configurable Filters**: Add minimum/maximum area and aspect ratio filters directly in the postprocessing pipeline (`DetectorConfig`).
3. **Integrate ByteTrack wrapper**: Ensure track continuity and occlusion handling to filter out single-frame noise.
4. **Refine Class Mappings**: Restrict detector output to exactly the 6 target COCO classes: `person`, `car`, `motorcycle`, `bus`, `truck`, `bicycle`, silently discarding all other classes and removing the generic `vehicle` or `object` labels.
5. **Create Metadata Exporter**: Standardize JSONL frame metadata and crop exports to prepare for future CLIP embedding searches.
