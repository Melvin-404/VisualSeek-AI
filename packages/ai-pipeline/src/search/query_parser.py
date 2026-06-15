import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

COLORS = ["red", "blue", "green", "yellow", "black", "white", "grey", "silver", "orange", "purple", "brown", "pink", "beige"]
VEHICLE_STYLES = ["suv", "sedan", "truck", "van", "motorcycle", "bus"]
PERSON_ATTRIBUTES = ["backpack", "bag", "umbrella", "jacket", "shirt", "pants", "shorts", "skirt", "hat", "helmet", "laptop", "phone", "vest", "hi-vis", "hard hat"]
CLASSES = ["person", "car", "bicycle", "motorcycle", "bus", "truck", "backpack"]

# Words that are both YOLO class labels AND person attributes.
# When person-context clues exist, these are treated as attributes, not classes.
AMBIGUOUS_CLASSES = {"backpack"}

CLASS_SYNONYMS = {
    "man": "person",
    "woman": "person",
    "child": "person",
    "people": "person",
    "individual": "person",
    "auto": "car",
    "vehicle": "car",
    "automobile": "car",
    "cab": "car",
    "taxi": "car",
    "forklift": "truck",
    "rider": "person",
    "cyclist": "person",
}

# Words that strongly signal a person-centric query context (excluding ambiguous classes to avoid self-reference)
_PERSON_CONTEXT_WORDS = ({"man", "woman", "child", "person", "people", "individual", "rider", "cyclist"} | set(PERSON_ATTRIBUTES)) - AMBIGUOUS_CLASSES

@dataclass
class SearchIntent:
    """Structured representation of a visual search query."""
    intent_type: str = "object_search"  # object_search, event_search, cross_camera_track
    object_class: Optional[str] = None
    color: Optional[str] = None
    vehicle_style: Optional[str] = None
    attributes: List[str] = field(default_factory=list)
    gender: Optional[str] = None
    spatial_zone: Optional[str] = None
    time_range_hours: Optional[float] = None
    raw_query: str = ""
    semantic_query: str = ""

class QueryParser:
    """Fast, offline, rule-based keyword query parser."""

    def parse(self, query: str) -> SearchIntent:
        query_clean = query.lower().strip()
        intent = SearchIntent(raw_query=query, semantic_query=query)

        # 1. Detect Cross-Camera Tracking intent
        if any(keyword in query_clean for keyword in ["same person", "same car", "same vehicle", "track the same", "cross-camera"]):
            intent.intent_type = "cross_camera_track"

        # 2. Extract spatial zones
        zone_match = re.search(r"zone[-_\s]([a-b])", query_clean)
        if zone_match:
            intent.spatial_zone = f"zone_{zone_match.group(1)}"

        # 3. Extract time ranges (e.g. "last 2 hours", "last hour", "past 3 hours")
        time_match = re.search(r"last\s+(\d+)\s+hours?", query_clean)
        if time_match:
            intent.time_range_hours = float(time_match.group(1))
        elif "last hour" in query_clean or "past hour" in query_clean:
            intent.time_range_hours = 1.0
        elif "today" in query_clean:
            intent.time_range_hours = 24.0

        # 4. Tokenize and extract class, colors, styles, and attributes
        words = re.findall(r"\b\w+\b", query_clean)

        # Pre-scan: detect if person-context clues exist in the query
        has_person_context = bool(set(words) & _PERSON_CONTEXT_WORDS)

        for word in words:
            # Match class label (skip ambiguous classes when person context is present)
            if word in CLASSES:
                if word in AMBIGUOUS_CLASSES and has_person_context:
                    # Treat as attribute instead of class when person context exists
                    pass
                else:
                    intent.object_class = word
            elif word in CLASS_SYNONYMS:
                intent.object_class = CLASS_SYNONYMS[word]
                # Special attribute injection based on synonym
                if word in ["man", "woman", "child"]:
                    intent.gender = word

            # Match color
            if word in COLORS:
                intent.color = word

            # Match vehicle style
            if word in VEHICLE_STYLES:
                intent.vehicle_style = word.upper()  # Database uses uppercase SUV, etc.

            # Match person attribute
            if word in PERSON_ATTRIBUTES:
                intent.attributes.append(word)

        # Handle compound attributes (e.g., "hard hat", "hi-vis vest")
        if "hard hat" in query_clean:
            intent.attributes.append("hard hat")
        if "hi-vis" in query_clean or "safety vest" in query_clean:
            intent.attributes.append("hi-vis vest")

        # Deduplicate attributes
        intent.attributes = list(set(intent.attributes))

        # Post-processing: resolve ambiguous class assignments
        # Only promote to person when non-ambiguous person attributes exist alongside
        if intent.object_class in AMBIGUOUS_CLASSES:
            non_ambiguous_attrs = [a for a in intent.attributes if a not in AMBIGUOUS_CLASSES]
            if non_ambiguous_attrs:
                intent.object_class = "person"

        # Infer object_class if attributes require it (e.g. backpack implies person class search)
        if intent.attributes and not intent.object_class:
            if any(attr in ["backpack", "umbrella", "jacket", "shirt", "pants", "shorts", "skirt", "hat", "laptop", "phone"] for attr in intent.attributes):
                intent.object_class = "person"

        # Infer object_class from vehicle_style (e.g. "yellow suv" -> class=car)
        if intent.vehicle_style and not intent.object_class:
            intent.object_class = "car"

        return intent
