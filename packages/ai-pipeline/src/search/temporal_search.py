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

    def analyze_action(self, session, hits: List[Dict[str, Any]], intent) -> List[Dict[str, Any]]:
        """
        For action queries (e.g. 'reversing'), attempts to validate the motion.
        Groups hits by track_id and queries the full track sequence to compute movement.
        Filters out stationary vehicles.
        Extracts temporal event windows (start to end of movement).
        Appends an honest verification status to the result metadata.
        """
        if not intent.is_action_query or not intent.action:
            return hits

        # Group initial hits by segment_id and track_id
        tracks_to_check = {}
        for hit in hits:
            # We must have a track_id to analyze motion
            track_id = hit.get("raw_labels", {}).get("detections", [{}])[0].get("track_id")
            if track_id is None:
                continue

            seg_id = hit.get("segment_id")
            key = (seg_id, track_id)
            if key not in tracks_to_check:
                tracks_to_check[key] = []
            tracks_to_check[key].append(hit)

        filtered_hits = []

        # Analyze each track's full temporal sequence
        for (seg_id, track_id), track_hits in tracks_to_check.items():
            # Query all bounding boxes for this track_id in this segment ordered by time
            # Note: We need to pull from the DB. DetectedObject has segment_id, track_id.
            db_tracks = session.query(DetectedObject).filter(
                DetectedObject.segment_id == seg_id,
                DetectedObject.track_id == track_id
            ).order_by(DetectedObject.frame_number).all()

            if not db_tracks or len(db_tracks) < 3:
                # Not enough frames to determine motion
                continue
            
            # Calculate total displacement from first to last frame
            first = db_tracks[0]
            last = db_tracks[-1]
            
            # center x,y = (bbox_x + (bbox_w/2))
            # Wait, the DB model schema: bbox_x, bbox_y, bbox_w, bbox_h
            cx_start = first.bbox_x + (first.bbox_w / 2)
            cy_start = first.bbox_y + (first.bbox_h / 2)
            
            cx_end = last.bbox_x + (last.bbox_w / 2)
            cy_end = last.bbox_y + (last.bbox_h / 2)
            
            # Normalized displacement distance
            displacement = ((cx_end - cx_start)**2 + (cy_end - cy_start)**2) ** 0.5
            
            # Threshold for considering it "moving" vs "stationary"
            # Since bbox is normalized [0, 1], displacement > 0.05 is ~5% of screen width
            if displacement < 0.05:
                # Vehicle is stationary, filter it out completely
                continue

            # It is moving! Set the event window based on the full track lifespan
            event_start_ms = first.timestamp_ms
            event_end_ms = last.timestamp_ms
            
            # Take the highest scoring hit from this track to represent it
            best_hit = max(track_hits, key=lambda h: h.get("score", 0))
            
            obj_class = intent.object_class or "Object"
            action = intent.action
            
            best_hit["event_start_ms"] = event_start_ms
            best_hit["event_end_ms"] = event_end_ms
            best_hit["action_status"] = f"{obj_class.capitalize()} detected moving, but '{action}' motion could not be reliably verified from 2D trajectory."
            best_hit["action_verified"] = False
            
            filtered_hits.append(best_hit)
            
        return filtered_hits

