import uuid
import numpy as np
import structlog
from typing import List, Dict, Any, Optional
from app.models.schema_models import IdentityGallery, DetectedObject

logger = structlog.get_logger("gallery_matcher")

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "suv", "van"}

class GalleryMatcher:
    """Matches ReID embeddings of detections to existing identities or creates new gallery profiles."""

    def __init__(self, person_threshold: float = 0.82, vehicle_threshold: float = 0.75):
        self.person_threshold = person_threshold
        self.vehicle_threshold = vehicle_threshold

    def match_and_update(self, session, obj: DetectedObject, embedding: np.ndarray) -> Optional[uuid.UUID]:
        """Matches a detection's ReID embedding against the identity gallery.
        
        Args:
            session: SQLAlchemy session.
            obj: The DetectedObject database record.
            embedding: Normalized 1D numpy array of shape (512,).
            
        Returns:
            The matched/created Gallery ID (UUID).
        """
        if embedding is None or len(embedding) == 0:
            return None

        # Determine object type
        class_label = obj.class_label.lower()
        if class_label == "person":
            object_type = "person"
            threshold = self.person_threshold
        elif class_label in VEHICLE_CLASSES:
            object_type = "vehicle"
            threshold = self.vehicle_threshold
        else:
            # ReID is only performed on persons and vehicles
            return None

        # Normalize the incoming embedding to be absolutely sure
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        else:
            return None

        # Query existing gallery items for this org and object type
        gallery_items = session.query(IdentityGallery).filter(
            IdentityGallery.org_id == obj.org_id,
            IdentityGallery.object_type == object_type
        ).all()

        best_sim = -1.0
        best_item = None

        for item in gallery_items:
            if item.reid_embedding is None:
                continue
            
            # Compute cosine similarity (dot product of normalized vectors)
            gallery_emb = np.array(item.reid_embedding, dtype=np.float32)
            sim = float(np.dot(embedding, gallery_emb))

            if sim > best_sim:
                best_sim = sim
                best_item = item

        logger.info(
            "Gallery matching attempt",
            object_id=str(obj.id),
            class_label=obj.class_label,
            best_similarity=round(best_sim, 4),
            threshold=threshold,
            matches_exist=len(gallery_items) > 0
        )

        if best_sim >= threshold and best_item is not None:
            # 1. Match found: update the entry's ReID embedding with a running average
            gallery_emb = np.array(best_item.reid_embedding, dtype=np.float32)
            alpha = 0.90  # Weight of historical embedding
            updated_emb = alpha * gallery_emb + (1 - alpha) * embedding
            
            # Normalize updated embedding
            updated_norm = np.linalg.norm(updated_emb)
            if updated_norm > 0:
                updated_emb = updated_emb / updated_norm
            
            best_item.reid_embedding = updated_emb.tolist()

            # Update metadata
            meta = best_item.gallery_metadata or {}
            meta["last_seen_segment"] = str(obj.segment_id)
            meta["last_seen_time"] = str(obj.created_at)
            
            # Track camera IDs seen
            cameras = meta.get("cameras_seen", [])
            camera_str = str(obj.segment_id)  # Using segment_id as cam link fallback
            if camera_str not in cameras:
                cameras.append(camera_str)
            meta["cameras_seen"] = cameras
            
            best_item.gallery_metadata = meta
            obj.gallery_id = best_item.id
            
            logger.info("Matched to existing gallery identity", gallery_id=str(best_item.id))
            return best_item.id
        else:
            # 2. No match: create a new gallery identity profile
            new_id = uuid.uuid4()
            meta = {
                "first_seen_segment": str(obj.segment_id),
                "first_seen_time": str(obj.created_at),
                "cameras_seen": [str(obj.segment_id)]
            }
            new_item = IdentityGallery(
                id=new_id,
                org_id=obj.org_id,
                object_type=object_type,
                reid_embedding=embedding.tolist(),
                gallery_metadata=meta
            )
            session.add(new_item)
            session.flush()  # Ensures new_item has database state populated
            obj.gallery_id = new_id
            
            logger.info("Created new gallery identity profile", gallery_id=str(new_id))
            return new_id
