import datetime
import uuid
from typing import List, Dict, Any, Optional

from sqlalchemy import func
from app.models.schema_models import DetectedObject, VideoSegment


class TemporalSearch:
    """Performs temporal trajectory analytics, entry/exit tracking, dwell time computation, and pathway queries."""

    def get_trajectory_path(self, session, gallery_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Computes the sequence of camera streams visited by a specific gallery identity chronologically."""
        # Query detections grouped by camera/segment to construct the chronological path
        results = (
            session.query(
                VideoSegment.camera_id,
                func.min(DetectedObject.segment_start_time).label("first_seen"),
                func.max(DetectedObject.segment_start_time).label("last_seen"),
                func.min(DetectedObject.timestamp_ms).label("min_ts"),
                func.max(DetectedObject.timestamp_ms).label("max_ts")
            )
            .join(VideoSegment, DetectedObject.segment_id == VideoSegment.id)
            .filter(DetectedObject.gallery_id == gallery_id)
            .group_by(VideoSegment.camera_id)
            .order_by("first_seen", "min_ts")
            .all()
        )

        pathway = []
        for idx, row in enumerate(results):
            # Compute approximate entry and exit datetime/timestamp
            entry_time = row.first_seen + datetime.timedelta(milliseconds=row.min_ts)
            exit_time = row.last_seen + datetime.timedelta(milliseconds=row.max_ts)
            dwell_ms = int((exit_time - entry_time).total_seconds() * 1000)

            pathway.append({
                "sequence_index": idx,
                "camera_id": str(row.camera_id),
                "entry_time": entry_time.isoformat(),
                "exit_time": exit_time.isoformat(),
                "dwell_time_ms": max(0, dwell_ms)
            })

        return pathway

    def get_camera_dwell_times(self, session, gallery_id: uuid.UUID) -> Dict[str, int]:
        """Calculates the total time spent by an identity in front of each camera in milliseconds."""
        path = self.get_trajectory_path(session, gallery_id)
        dwell_times = {}
        for leg in path:
            cam = leg["camera_id"]
            dwell_times[cam] = dwell_times.get(cam, 0) + leg["dwell_time_ms"]
        return dwell_times

    def find_objects_by_trajectory(self, session, camera_sequence: List[str]) -> List[Dict[str, Any]]:
        """Finds gallery profiles that visited the specified list of cameras in that chronological order."""
        if not camera_sequence or len(camera_sequence) < 2:
            return []

        # Find all gallery_ids that visited the first camera
        # Then verify they visited subsequent cameras in sequence
        # Fetch all detections belonging to any gallery ID that has a ReID record
        gallery_ids_query = session.query(DetectedObject.gallery_id).filter(DetectedObject.gallery_id.isnot(None)).distinct()
        all_gallery_ids = [r[0] for r in gallery_ids_query.all()]

        matching_profiles = []
        for g_id in all_gallery_ids:
            path = self.get_trajectory_path(session, g_id)
            if not path:
                continue

            # Check if camera_sequence is a subsequence of the path cameras
            path_cameras = [leg["camera_id"] for leg in path]
            
            # Subsequence matching algorithm
            it = iter(path_cameras)
            if all(cam in it for cam in camera_sequence):
                matching_profiles.append({
                    "gallery_id": str(g_id),
                    "full_path": path_cameras,
                    "matched_sequence": camera_sequence
                })

        return matching_profiles

    def find_dwell_time_anomalies(self, session, min_dwell_minutes: float = 5.0) -> List[Dict[str, Any]]:
        """Identifies any gallery identity whose dwell time on a single camera exceeds the normal threshold."""
        min_dwell_ms = min_dwell_minutes * 60 * 1000
        
        gallery_ids_query = session.query(DetectedObject.gallery_id).filter(DetectedObject.gallery_id.isnot(None)).distinct()
        all_gallery_ids = [r[0] for r in gallery_ids_query.all()]

        anomalies = []
        for g_id in all_gallery_ids:
            path = self.get_trajectory_path(session, g_id)
            for leg in path:
                if leg["dwell_time_ms"] >= min_dwell_ms:
                    anomalies.append({
                        "gallery_id": str(g_id),
                        "camera_id": leg["camera_id"],
                        "dwell_time_ms": leg["dwell_time_ms"],
                        "dwell_time_minutes": round(leg["dwell_time_ms"] / 60000.0, 2),
                        "entry_time": leg["entry_time"],
                        "exit_time": leg["exit_time"]
                    })

        return anomalies
