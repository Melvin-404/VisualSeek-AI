"""Frame metadata exporter to JSONL format.

This module provides the FrameMetadataExporter class, which handles incremental,
thread-safe exportation of detection metadata to a JSONL file.
"""

import json
import logging
from pathlib import Path
from threading import Lock
from typing import List

# Import Detection class from detectors package
from detectors.yolo_detector import Detection

logger = logging.getLogger(__name__)

class FrameMetadataExporter:
    """Handles incremental, thread-safe exporting of frame detection metadata to a JSONL file."""

    def __init__(self, output_path: str):
        """Initialize the exporter and ensure the output directory exists.

        Args:
            output_path: Path to the destination .jsonl file.
        """
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        
        logger.info("FrameMetadataExporter initialised at output path: %s", self.output_path.resolve())

    def export_frame(
        self,
        frame_id: int,
        timestamp_ms: float,
        camera_id: str,
        detections: List[Detection]
    ) -> None:
        """Write frame metadata and its detections to the JSONL file as a single line.

        This method is thread-safe.

        Args:
            frame_id: Monotonically increasing frame counter.
            timestamp_ms: Capture timestamp in milliseconds.
            camera_id: Identifier string for the camera stream.
            detections: List of Detection objects for the current frame.
        """
        # Serialize all detections using their defined to_dict() method
        serialized_detections = [det.to_dict() for det in detections]
        
        frame_record = {
            "frame_id": frame_id,
            "timestamp_ms": round(timestamp_ms, 2),
            "camera_id": camera_id,
            "detections": serialized_detections
        }

        # Convert to string and append newline
        json_line = json.dumps(frame_record, ensure_ascii=False) + "\n"

        # Thread-safe append write to the output file
        with self._lock:
            try:
                with open(self.output_path, "a", encoding="utf-8") as f:
                    f.write(json_line)
            except Exception as e:
                logger.error(
                    "Failed to write frame metadata line for frame_id=%d: %s",
                    frame_id,
                    e
                )
                raise
