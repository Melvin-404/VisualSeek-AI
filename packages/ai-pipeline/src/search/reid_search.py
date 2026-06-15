import datetime
import uuid
import sqlalchemy as sa
from typing import List, Dict, Any, Optional

from app.models.schema_models import DetectedObject, IdentityGallery, VideoSegment


class ReIDSearch:
    """Performs cross-camera identity tracking and gallery search using ReID embeddings and database records."""

    def search_by_gallery_id(
        self,
        session,
        gallery_id: uuid.UUID,
        allowed_camera_ids: Optional[List[str]] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Traces the trajectory of a specific gallery identity across camera streams chronologically."""
        query = session.query(DetectedObject).filter(DetectedObject.gallery_id == gallery_id)

        # Camera restriction
        if allowed_camera_ids is not None:
            subquery = session.query(VideoSegment.id).filter(VideoSegment.camera_id.in_(allowed_camera_ids)).subquery()
            query = query.filter(DetectedObject.segment_id.in_(subquery))

        # Time range restriction
        if start_time:
            query = query.filter(DetectedObject.segment_start_time >= start_time)
        if end_time:
            query = query.filter(DetectedObject.segment_start_time <= end_time)

        # Order chronologically to map the path/trajectory
        results = query.order_by(DetectedObject.segment_start_time.asc(), DetectedObject.timestamp_ms.asc()).limit(limit).all()

        hits = []
        for obj in results:
            hit = {
                "id": str(obj.id),
                "camera_id": None,  # Will be mapped to camera_id in the search coordinator
                "timestamp_ms": obj.timestamp_ms,
                "frame_number": obj.frame_number,
                "segment_id": str(obj.segment_id),
                "class_label": obj.class_label,
                "confidence": obj.confidence,
                "bbox": [obj.bbox_x, obj.bbox_y, obj.bbox_w, obj.bbox_h],
                "dominant_colour": obj.dominant_colour,
                "vehicle_type": obj.vehicle_type,
                "upper_colour": obj.upper_colour,
                "lower_colour": obj.lower_colour,
                "carried_items": obj.carried_items or [],
                "gender_estimate": obj.gender_estimate,
                "gallery_id": str(obj.gallery_id),
                "created_at": obj.created_at.isoformat() if obj.created_at else None,
                "search_source": "reid_trajectory"
            }
            hits.append(hit)

        return hits

    def search_by_embedding(
        self,
        session,
        embedding: List[float],
        object_type: str = "person",
        allowed_camera_ids: Optional[List[str]] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        threshold: float = 0.80,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Queries the identity gallery using cosine distance to find matching profiles, then fetches all occurrences."""
        # 1. Query IdentityGallery for matching IDs
        distance_expr = IdentityGallery.reid_embedding.cosine_distance(embedding)
        
        # similarity = 1 - cosine_distance. So similarity >= threshold -> distance <= 1 - threshold
        gallery_query = session.query(IdentityGallery, (1 - distance_expr).label("similarity"))
        gallery_query = gallery_query.filter(IdentityGallery.object_type == object_type)
        gallery_query = gallery_query.filter(distance_expr <= (1.0 - threshold))
        
        gallery_matches = gallery_query.order_by(distance_expr.asc()).limit(10).all()
        
        if not gallery_matches:
            # Let's perform a direct search in detected_objects table as fallback
            obj_distance = DetectedObject.reid_embedding.cosine_distance(embedding)
            obj_query = session.query(DetectedObject, (1 - obj_distance).label("similarity"))
            obj_query = obj_query.filter(DetectedObject.class_label == object_type)
            obj_query = obj_query.filter(obj_distance <= (1.0 - threshold))
            
            if allowed_camera_ids is not None:
                subquery = session.query(VideoSegment.id).filter(VideoSegment.camera_id.in_(allowed_camera_ids)).subquery()
                obj_query = obj_query.filter(DetectedObject.segment_id.in_(subquery))
                
            if start_time:
                obj_query = obj_query.filter(DetectedObject.segment_start_time >= start_time)
            if end_time:
                obj_query = obj_query.filter(DetectedObject.segment_start_time <= end_time)
                
            obj_results = obj_query.order_by(obj_distance.asc()).limit(limit).all()
            
            hits = []
            for obj, sim in obj_results:
                hit = {
                    "id": str(obj.id),
                    "camera_id": None,
                    "timestamp_ms": obj.timestamp_ms,
                    "frame_number": obj.frame_number,
                    "segment_id": str(obj.segment_id),
                    "class_label": obj.class_label,
                    "confidence": obj.confidence,
                    "bbox": [obj.bbox_x, obj.bbox_y, obj.bbox_w, obj.bbox_h],
                    "dominant_colour": obj.dominant_colour,
                    "vehicle_type": obj.vehicle_type,
                    "upper_colour": obj.upper_colour,
                    "lower_colour": obj.lower_colour,
                    "carried_items": obj.carried_items or [],
                    "gender_estimate": obj.gender_estimate,
                    "gallery_id": str(obj.gallery_id) if obj.gallery_id else None,
                    "score": float(sim),
                    "created_at": obj.created_at.isoformat() if obj.created_at else None,
                    "search_source": "reid_direct"
                }
                hits.append(hit)
            return hits

        # 2. If gallery profiles are found, trace all occurrences for the matched gallery identities
        matched_gallery_ids = [gallery.id for gallery, _ in gallery_matches]
        gallery_similarities = {str(gallery.id): float(sim) for gallery, sim in gallery_matches}

        query = session.query(DetectedObject).filter(DetectedObject.gallery_id.in_(matched_gallery_ids))

        # Camera restriction
        if allowed_camera_ids is not None:
            subquery = session.query(VideoSegment.id).filter(VideoSegment.camera_id.in_(allowed_camera_ids)).subquery()
            query = query.filter(DetectedObject.segment_id.in_(subquery))

        # Time range restriction
        if start_time:
            query = query.filter(DetectedObject.segment_start_time >= start_time)
        if end_time:
            query = query.filter(DetectedObject.segment_start_time <= end_time)

        results = query.order_by(DetectedObject.segment_start_time.desc(), DetectedObject.timestamp_ms.desc()).limit(limit).all()

        hits = []
        for obj in results:
            g_id = str(obj.gallery_id)
            score = gallery_similarities.get(g_id, threshold)
            hit = {
                "id": str(obj.id),
                "camera_id": None,
                "timestamp_ms": obj.timestamp_ms,
                "frame_number": obj.frame_number,
                "segment_id": str(obj.segment_id),
                "class_label": obj.class_label,
                "confidence": obj.confidence,
                "bbox": [obj.bbox_x, obj.bbox_y, obj.bbox_w, obj.bbox_h],
                "dominant_colour": obj.dominant_colour,
                "vehicle_type": obj.vehicle_type,
                "upper_colour": obj.upper_colour,
                "lower_colour": obj.lower_colour,
                "carried_items": obj.carried_items or [],
                "gender_estimate": obj.gender_estimate,
                "gallery_id": g_id,
                "score": score,
                "created_at": obj.created_at.isoformat() if obj.created_at else None,
                "search_source": "reid_gallery"
            }
            hits.append(hit)

        # Sort hits by similarity score descending
        hits = sorted(hits, key=lambda x: x.get("score", 0.0), reverse=True)
        return hits
