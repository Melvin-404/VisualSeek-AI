import datetime
import sqlalchemy as sa
from typing import List, Dict, Any, Optional
from app.models.schema_models import DetectedObject, Camera, VideoSegment
from search.query_parser import SearchIntent

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "suv", "van"}

class MetadataSearch:
    """Performs dynamic SQL query assembly and execution for structured metadata search in PostgreSQL."""

    def search(
        self,
        session,
        intent: SearchIntent,
        allowed_camera_ids: Optional[List[str]] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Queries detected_objects table in PostgreSQL based on extracted metadata search intent."""
        query = session.query(DetectedObject)

        # 1. Class label filtering with synonyms
        if intent.object_class:
            cls = intent.object_class.lower()
            if cls == "car":
                # Match car or vehicle or other vehicle subtypes
                query = query.filter(DetectedObject.class_label.in_(["car", "vehicle"]))
            else:
                query = query.filter(sa.func.lower(DetectedObject.class_label) == cls)

        # 2. Color filtering
        if intent.color:
            color = intent.color.lower()
            if intent.object_class == "person":
                # For persons, color can be upper, lower or dominant
                query = query.filter(
                    sa.or_(
                        sa.func.lower(DetectedObject.upper_colour) == color,
                        sa.func.lower(DetectedObject.lower_colour) == color,
                        sa.func.lower(DetectedObject.dominant_colour) == color
                    )
                )
            else:
                query = query.filter(sa.func.lower(DetectedObject.dominant_colour) == color)

        # 3. Vehicle style filtering
        if intent.vehicle_style:
            query = query.filter(sa.func.lower(DetectedObject.vehicle_type) == intent.vehicle_style.lower())

        # 4. Person attributes filtering (JSONB carried_items array lookup)
        if intent.attributes:
            for attr in intent.attributes:
                # Use carried_items ? 'attribute' PostgreSQL jsonb check
                query = query.filter(DetectedObject.carried_items.has_key(attr))

        # 5. Gender filtering
        if intent.gender:
            query = query.filter(sa.func.lower(DetectedObject.gender_estimate) == intent.gender.lower())

        # 6. Camera filtering (multi-tenancy and Operator constraints)
        if allowed_camera_ids is not None:
            # We must map camera_ids through the video segment relationship
            subquery = session.query(VideoSegment.id).filter(VideoSegment.camera_id.in_(allowed_camera_ids)).subquery()
            query = query.filter(DetectedObject.segment_id.in_(subquery))

        # 7. Time range filtering (on segment start time)
        if start_time:
            query = query.filter(DetectedObject.segment_start_time >= start_time)
        if end_time:
            query = query.filter(DetectedObject.segment_start_time <= end_time)

        # Execute query
        results = query.order_by(DetectedObject.confidence.desc()).limit(limit).all()

        # Format results to unified list of dicts
        hits = []
        for obj in results:
            hit = {
                "id": str(obj.id),
                "camera_id": None,  # Will be mapped in search engine
                "timestamp_ms": obj.timestamp_ms,
                "frame_number": obj.frame_number,
                "segment_id": str(obj.segment_id),
                "class_label": obj.class_label,
                "confidence": obj.confidence,
                "bbox": [obj.bbox_x, obj.bbox_y, obj.bbox_w, obj.bbox_h],
                "dominant_colour": obj.dominant_colour,
                "colour_confidence": obj.colour_confidence,
                "vehicle_type": obj.vehicle_type,
                "vehicle_type_confidence": obj.vehicle_type_confidence,
                "upper_colour": obj.upper_colour,
                "upper_colour_conf": obj.upper_colour_conf,
                "lower_colour": obj.lower_colour,
                "lower_colour_conf": obj.lower_colour_conf,
                "carried_items": obj.carried_items or [],
                "gender_estimate": obj.gender_estimate,
                "gallery_id": str(obj.gallery_id) if obj.gallery_id else None,
                "created_at": obj.created_at.isoformat() if obj.created_at else None,
                "search_source": "metadata"
            }
            hits.append(hit)

        return hits
