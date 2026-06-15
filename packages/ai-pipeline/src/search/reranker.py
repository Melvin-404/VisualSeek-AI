import math
import time
from typing import List, Dict, Any, Optional
from search.query_parser import SearchIntent


class SearchReranker:
    """Combines metadata matches, semantic similarity, and temporal decay to rank visual search hits."""

    def rerank(
        self,
        intent: SearchIntent,
        hits: List[Dict[str, Any]],
        target_time: Optional[float] = None,  # Epoch timestamp in milliseconds
        half_life_hours: float = 24.0
    ) -> List[Dict[str, Any]]:
        """Applies multi-factor re-ranking on search hits."""
        if not hits:
            return []

        # Default target_time to now (in milliseconds)
        if target_time is None:
            target_time = time.time() * 1000.0

        scored_hits = []
        for hit in hits:
            # 1. Semantic score (default to 0.5 if not present)
            semantic_score = hit.get("score", 0.5)
            # Normalise to [0.0, 1.0]
            semantic_score = max(0.0, min(1.0, semantic_score))

            # 2. Metadata attribute match score
            metadata_score = 0.0
            total_checks = 0
            matches = 0

            # Class check
            if intent.object_class:
                total_checks += 1
                cls_label = hit.get("class_label", "").lower()
                # Also check object_classes list if present in frame search
                obj_classes = hit.get("object_classes", []) or []
                obj_classes_lower = [c.lower() for c in obj_classes]
                
                if cls_label == intent.object_class.lower() or intent.object_class.lower() in obj_classes_lower:
                    matches += 1
                elif intent.object_class.lower() == "car" and (cls_label in ["vehicle", "automobile"] or any(c in obj_classes_lower for c in ["car", "vehicle"])):
                    matches += 1

            # Color check (dominant, upper, lower)
            if intent.color:
                total_checks += 1
                color = intent.color.lower()
                hit_colors = [
                    hit.get("dominant_colour"),
                    hit.get("upper_colour"),
                    hit.get("lower_colour")
                ]
                hit_colors = [c.lower() for c in hit_colors if c]
                if color in hit_colors:
                    matches += 1

            # Vehicle style check
            if intent.vehicle_style:
                total_checks += 1
                v_style = hit.get("vehicle_type", "").lower()
                if v_style == intent.vehicle_style.lower():
                    matches += 1

            # Carried items check
            if intent.attributes:
                for attr in intent.attributes:
                    total_checks += 1
                    carried = hit.get("carried_items", []) or []
                    if isinstance(carried, dict):
                        carried_list = list(carried.keys())
                    else:
                        carried_list = list(carried)
                    carried_list = [c.lower() for c in carried_list]
                    if attr.lower() in carried_list:
                        matches += 1

            # Gender check
            if intent.gender:
                total_checks += 1
                gender = hit.get("gender_estimate", "").lower()
                if gender == intent.gender.lower():
                    matches += 1

            if total_checks > 0:
                metadata_score = matches / total_checks
            else:
                metadata_score = 1.0

            # 3. Temporal decay
            hit_ts = hit.get("timestamp_ms", 0)
            if not hit_ts and "first_seen" in hit:
                hit_ts = hit["first_seen"]
            
            if not hit_ts:
                hit_ts = target_time

            # Calculate absolute difference in hours
            diff_hours = abs(target_time - hit_ts) / (3600.0 * 1000.0)
            # Exponential decay formula: e^(-ln(2) * t / half_life)
            temporal_decay = math.exp(-0.693 * diff_hours / half_life_hours)

            # 4. Combined weighted score: 40% Semantic, 40% Metadata, 20% Temporal Decay
            combined_score = 0.4 * semantic_score + 0.4 * metadata_score + 0.2 * temporal_decay

            # Copy hit and append scores
            hit_copy = hit.copy()
            hit_copy["rerank_score"] = float(combined_score)
            hit_copy["semantic_score"] = float(semantic_score)
            hit_copy["metadata_score"] = float(metadata_score)
            hit_copy["temporal_decay"] = float(temporal_decay)
            
            scored_hits.append(hit_copy)

        # Sort descending by combined rerank_score
        scored_hits = sorted(scored_hits, key=lambda x: x["rerank_score"], reverse=True)
        return scored_hits
