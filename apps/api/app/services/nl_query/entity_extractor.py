"""SpaCy-based entity extractor for surveillance domain.

Extracts colors, clothing, vehicle types, and behavioral attributes
from query text using spaCy NLP and rule-based matchers.
Falls back to regex word matching if spaCy is unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

import structlog

logger = structlog.get_logger("nl_query.entity_extractor")

# --- Domain Vocabularies ---

COLOR_TERMS = {
    "red", "blue", "green", "yellow", "orange", "purple", "pink", "black",
    "white", "gray", "grey", "brown", "silver", "gold", "beige", "navy",
    "maroon", "teal", "cyan", "magenta", "olive", "burgundy", "tan",
    "khaki", "dark", "light", "bright", "neon",
}

CLOTHING_TERMS = {
    "jacket", "coat", "hoodie", "sweater", "shirt", "t-shirt", "tshirt",
    "vest", "uniform", "dress", "skirt", "pants", "jeans", "shorts",
    "hat", "cap", "helmet", "mask", "scarf", "gloves", "glasses",
    "sunglasses", "backpack", "bag", "handbag", "briefcase", "purse",
    "suitcase", "luggage", "boots", "shoes", "sneakers", "sandals",
    "high-vis", "reflective", "apron", "hard hat", "headband",
}

VEHICLE_TYPES = {
    "sedan", "suv", "truck", "van", "bus", "motorcycle", "bike", "bicycle",
    "minivan", "pickup", "hatchback", "coupe", "convertible", "wagon",
    "jeep", "taxi", "ambulance", "police car", "fire truck", "scooter",
    "moped", "skateboard", "e-scooter", "forklift", "tractor", "trailer",
    "semi", "lorry", "rig", "rv", "camper",
}

BEHAVIOR_TERMS = {
    "running", "walking", "standing", "sitting", "loitering", "fighting",
    "falling", "crawling", "jumping", "climbing", "entering", "exiting",
    "crossing", "waiting", "talking", "smoking", "carrying", "dropping",
    "throwing", "pushing", "pulling", "dragging", "following", "chasing",
    "hiding", "crouching", "kneeling", "lying", "sleeping", "waving",
    "pointing", "gesturing", "arguing", "shoplifting", "trespassing",
    "vandalizing", "speeding", "parking", "driving", "stopped",
}

OBJECT_CLASSES = {
    "person", "people", "man", "woman", "child", "kid", "pedestrian",
    "car", "vehicle", "truck", "bus", "bicycle", "motorcycle",
    "dog", "cat", "bird", "animal",
    "backpack", "suitcase", "luggage", "bag", "package", "box",
    "phone", "laptop", "umbrella", "bottle", "gun", "knife", "weapon",
    "fire", "smoke", "flame",
}


@dataclass
class ExtractedEntities:
    """Entities extracted from a surveillance query."""

    colors: List[str] = field(default_factory=list)
    clothing: List[str] = field(default_factory=list)
    vehicle_types: List[str] = field(default_factory=list)
    behaviors: List[str] = field(default_factory=list)
    object_classes: List[str] = field(default_factory=list)
    quantities: List[int] = field(default_factory=list)
    raw_text: str = ""

    def to_context_string(self) -> str:
        """Produce a compact summary string for LLM prompt augmentation."""
        parts = []
        if self.object_classes:
            parts.append(f"Objects: {', '.join(self.object_classes)}")
        if self.colors:
            parts.append(f"Colors: {', '.join(self.colors)}")
        if self.clothing:
            parts.append(f"Clothing: {', '.join(self.clothing)}")
        if self.vehicle_types:
            parts.append(f"Vehicle types: {', '.join(self.vehicle_types)}")
        if self.behaviors:
            parts.append(f"Behaviors: {', '.join(self.behaviors)}")
        if self.quantities:
            parts.append(f"Quantities: {', '.join(str(q) for q in self.quantities)}")
        return "; ".join(parts) if parts else "No specific entities detected."


class SpaCyEntityExtractor:
    """Extracts surveillance-domain entities from query text.

    Uses spaCy NLP with rule-based matchers when available.
    Falls back gracefully to regex-based extraction if spaCy is unavailable.
    """

    def __init__(self):
        self._nlp = None
        self._spacy_available = False
        self._init_spacy()

    def _init_spacy(self):
        """Attempt to load spaCy's en_core_web_sm model."""
        try:
            import spacy  # type: ignore[import-untyped]

            try:
                self._nlp = spacy.load("en_core_web_sm")
                self._spacy_available = True
                logger.info("spaCy en_core_web_sm model loaded successfully.")
            except OSError:
                logger.info("en_core_web_sm not found. Attempting download...")
                try:
                    import subprocess
                    import sys

                    subprocess.check_call(
                        [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self._nlp = spacy.load("en_core_web_sm")
                    self._spacy_available = True
                    logger.info("en_core_web_sm downloaded and loaded.")
                except Exception as e:
                    logger.warning(
                        "spaCy model download failed. Falling back to regex extraction.",
                        error=str(e),
                    )
        except ImportError:
            logger.warning("spaCy not installed. Using regex-only entity extraction.")

    def extract(self, text: str) -> ExtractedEntities:
        """Extract domain-specific entities from free-text query."""
        if not text:
            return ExtractedEntities()

        entities = ExtractedEntities(raw_text=text)
        text_lower = text.lower()
        tokens = set(re.findall(r"\b\w+(?:-\w+)*\b", text_lower))

        # --- Color extraction ---
        entities.colors = sorted(tokens & COLOR_TERMS)

        # Also check two-word color phrases
        for phrase in ["dark blue", "light blue", "dark green", "light green",
                       "dark red", "bright red", "neon green", "navy blue"]:
            if phrase in text_lower:
                entities.colors.append(phrase)

        # --- Clothing extraction ---
        entities.clothing = sorted(tokens & CLOTHING_TERMS)
        # Multi-word clothing
        for phrase in ["hard hat", "high-vis", "t-shirt"]:
            if phrase in text_lower and phrase not in entities.clothing:
                entities.clothing.append(phrase)

        # --- Vehicle type extraction ---
        entities.vehicle_types = sorted(tokens & VEHICLE_TYPES)
        for phrase in ["police car", "fire truck", "e-scooter"]:
            if phrase in text_lower and phrase not in entities.vehicle_types:
                entities.vehicle_types.append(phrase)

        # --- Behavior extraction ---
        entities.behaviors = sorted(tokens & BEHAVIOR_TERMS)

        # --- Object class extraction ---
        entities.object_classes = sorted(tokens & OBJECT_CLASSES)

        # --- Quantity extraction ---
        qty_matches = re.findall(r"\b(\d+)\s+(?:people|persons?|cars?|vehicles?|trucks?)\b", text_lower)
        entities.quantities = [int(q) for q in qty_matches]

        # --- spaCy NER augmentation ---
        if self._spacy_available and self._nlp is not None:
            try:
                doc = self._nlp(text)
                for ent in doc.ents:
                    ent_lower = ent.text.lower()
                    if ent.label_ == "CARDINAL":
                        try:
                            val = int(ent.text)
                            if val not in entities.quantities:
                                entities.quantities.append(val)
                        except ValueError:
                            pass
                    elif ent.label_ in ("GPE", "LOC", "FAC"):
                        # Location entities could indicate spatial zones
                        pass  # handled by spatial_zone in the main parser
            except Exception as e:
                logger.warning("spaCy NER extraction failed.", error=str(e))

        # Deduplicate
        entities.colors = sorted(set(entities.colors))
        entities.clothing = sorted(set(entities.clothing))
        entities.vehicle_types = sorted(set(entities.vehicle_types))
        entities.behaviors = sorted(set(entities.behaviors))
        entities.object_classes = sorted(set(entities.object_classes))

        return entities
