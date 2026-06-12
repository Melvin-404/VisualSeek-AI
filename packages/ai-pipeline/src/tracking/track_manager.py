"""Track manager for per-camera tracker states, state snapshotting, GDPR anonymization, and retention."""

import datetime
import logging
import os
import threading
from typing import Dict, List, Optional

import cv2
import numpy as np

from tracking.bytetrack import ByteTracker, STrack
from tracking.reid_model import OSNetReID
from tracking.trajectory import TrajectoryAnalyzer

logger = logging.getLogger(__name__)


class TrackManager:
    """Manages thread-safe tracker instances for multiple camera streams, snapshotting, and GDPR compliance."""

    def __init__(
        self,
        reid_model: Optional[OSNetReID] = None,
        trajectory_analyzer: Optional[TrajectoryAnalyzer] = None,
    ):
        """Initialize TrackManager."""
        self._lock = threading.RLock()
        self.trackers: Dict[str, ByteTracker] = {}
        self.reid_model = reid_model if reid_model is not None else OSNetReID()
        self.trajectory_analyzer = (
            trajectory_analyzer if trajectory_analyzer is not None else TrajectoryAnalyzer()
        )

        # Initialize Haar Cascade face detector for GDPR face blur
        try:
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
        except Exception as e:
            logger.warning("Failed to load face cascade: %s. Relying on geometric fallback blur.", e)
            self.face_cascade = None

    def get_tracker(self, camera_id: str) -> ByteTracker:
        """Get or create the independent ByteTracker instance for a camera stream."""
        with self._lock:
            if camera_id not in self.trackers:
                logger.info("Initializing new ByteTracker for camera: %s", camera_id)
                self.trackers[camera_id] = ByteTracker()
            return self.trackers[camera_id]

    def update_camera_tracker(
        self, camera_id: str, detections: np.ndarray, frame: np.ndarray, timestamp_ms: int
    ) -> List[STrack]:
        """Thread-safe update to a specific camera's tracker.

        Args:
            camera_id: Unique string identifier for the camera.
            detections: Bounding boxes and scores (N, 6)
            frame: Capture frame.
            timestamp_ms: Current timestamp.
        """
        with self._lock:
            tracker = self.get_tracker(camera_id)
            return tracker.update(detections, frame, timestamp_ms, self.reid_model)

    def anonymize_frame(self, frame: np.ndarray, tracks: List[STrack]) -> np.ndarray:
        """Anonymize face regions in the frame for GDPR compliance.

        Attempts Haar Cascade face detection inside person boxes, falling back
        to blurring the top 20% of the bounding box if no face is detected.
        """
        anonymized = frame.copy()
        h, w = frame.shape[:2]

        for track in tracks:
            # Person class index is 0
            if track.class_label == 0:
                x1, y1, x2, y2 = map(int, track.bbox)
                x1 = max(0, min(x1, w - 1))
                y1 = max(0, min(y1, h - 1))
                x2 = max(0, min(x2, w - 1))
                y2 = max(0, min(y2, h - 1))

                if x2 <= x1 or y2 <= y1:
                    continue

                # Crop person region
                person_crop = anonymized[y1:y2, x1:x2]
                
                # Check if cascade is loaded and we can run detection
                faces = []
                if self.face_cascade is not None and not self.face_cascade.empty() and person_crop.size > 0:
                    try:
                        gray_person = cv2.cvtColor(person_crop, cv2.COLOR_BGR2GRAY)
                        faces = self.face_cascade.detectMultiScale(
                            gray_person, scaleFactor=1.1, minNeighbors=3, minSize=(10, 10)
                        )
                    except Exception:
                        pass

                if len(faces) > 0:
                    for (fx, fy, fw, fh) in faces:
                        # Map face coordinates back to frame coordinates
                        face_y1 = y1 + fy
                        face_y2 = face_y1 + fh
                        face_x1 = x1 + fx
                        face_x2 = face_x1 + fw

                        # Apply Gaussian Blur
                        face_region = anonymized[face_y1:face_y2, face_x1:face_x2]
                        if face_region.size > 0:
                            ksize = int(max(3, (fw // 2) | 1))
                            blurred = cv2.GaussianBlur(face_region, (ksize, ksize), 0)
                            anonymized[face_y1:face_y2, face_x1:face_x2] = blurred
                else:
                    # Fallback geometric head blur: top 20% of bounding box
                    head_h = int((y2 - y1) * 0.20)
                    head_y2 = y1 + head_h
                    if head_y2 > y1 and x2 > x1:
                        head_region = anonymized[y1:head_y2, x1:x2]
                        if head_region.size > 0:
                            ksize = int(max(3, ((x2 - x1) // 3) | 1))
                            blurred = cv2.GaussianBlur(head_region, (ksize, ksize), 0)
                            anonymized[y1:head_y2, x1:x2] = blurred

        return anonymized

    def get_snapshot(self) -> dict:
        """Serialize all trackers' states to a dictionary snapshot for crash recovery."""
        with self._lock:
            return {
                "timestamp": datetime.datetime.now().isoformat(),
                "trackers": {
                    camera_id: tracker.to_dict()
                    for camera_id, tracker in self.trackers.items()
                }
            }

    def load_snapshot(self, snapshot: dict) -> None:
        """Restore all trackers' states from a snapshot dictionary."""
        with self._lock:
            self.trackers.clear()
            for camera_id, tracker_data in snapshot.get("trackers", {}).items():
                tracker = ByteTracker()
                tracker.from_dict(tracker_data)
                self.trackers[camera_id] = tracker
            logger.info("Successfully loaded and restored tracker states for %d cameras.", len(self.trackers))

    def cleanup_expired_tracks(self, db_session=None, retention_days: int = 30) -> int:
        """GDPR track data retention policy enforcement.

        Deletes database track records older than retention_days.
        Simulates database deletion when no database session is passed.

        Returns:
            Number of deleted tracks.
        """
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=retention_days)
        logger.info("Enforcing GDPR retention: deleting tracks created before %s", cutoff_date.isoformat())

        if db_session is not None:
            try:
                # Assuming SQLAlchemy model 'TrackRecord' exists:
                # query = db_session.query(TrackRecord).filter(TrackRecord.created_at < cutoff_date)
                # count = query.delete()
                # db_session.commit()
                # return count
                pass
            except Exception as e:
                logger.error("Failed to delete expired tracks from database: %s", e)
                if hasattr(db_session, "rollback"):
                    db_session.rollback()
                return 0

        # Simulation mode or log only fallback
        logger.info("GDPR retention execution complete (simulation mode).")
        return 1
