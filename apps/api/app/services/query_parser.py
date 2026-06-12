import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger("query_parser")

# Domain dictionary fallback for surveillance classes
SYNONYM_FALLBACK = {
    "car": ["vehicle", "automobile", "motorcar", "sedan", "suv"],
    "truck": ["vehicle", "pickup", "lorry", "carrier", "semi"],
    "vehicle": ["car", "truck", "bus", "van", "automobile"],
    "person": ["man", "woman", "pedestrian", "human", "child", "people"],
    "man": ["person", "human", "pedestrian"],
    "woman": ["person", "human", "pedestrian"],
    "pedestrian": ["person", "pedestrian", "human", "walker"],
    "backpack": ["bag", "luggage", "pack", "sack"],
    "luggage": ["bag", "suitcase", "backpack", "handbag", "briefcase"],
    "suitcase": ["luggage", "bag", "backpack"],
    "bicycle": ["bike", "cycle", "two-wheeler"],
    "bike": ["bicycle", "motorcycle", "cycle"],
    "fire": ["smoke", "flame", "blaze", "heat"],
    "smoke": ["fire", "haze", "exhaust"],
    "dog": ["animal", "pet", "canine"],
    "cat": ["animal", "pet", "feline"],
}

# Supported class list (known taxonomy)
SURVEILLANCE_CLASSES = {
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
    "chair", "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop",
    "mouse", "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush", "luggage", "vehicle", "fire", "smoke", "van"
}


@dataclass
class ParsedQuery:
    raw_query: str
    semantic_query: str = ""
    classes: List[str] = field(default_factory=list)
    excluded_classes: List[str] = field(default_factory=list)
    start_time: Optional[int] = None
    end_time: Optional[int] = None
    camera_ids: List[str] = field(default_factory=list)
    spatial_zone: Optional[str] = None
    expanded_synonyms: List[str] = field(default_factory=list)


class QueryParser:
    """Parses natural language search queries to extract semantic search strings and structured metadata filters."""

    def __init__(self):
        self.wordnet_enabled = False
        try:
            import nltk
            # Set local path to download NLTK data safely if needed
            import os
            nltk_data_dir = os.path.join(os.path.expanduser("~"), "nltk_data")
            if nltk_data_dir not in nltk.data.path:
                nltk.data.path.append(nltk_data_dir)
            
            # Try loading WordNet
            from nltk.corpus import wordnet
            try:
                wordnet.synsets("car")
                self.wordnet_enabled = True
                logger.info("NLTK WordNet is loaded and ready.")
            except LookupError:
                logger.info("NLTK WordNet not found locally. Attempting silent download...")
                nltk.download("wordnet", download_dir=nltk_data_dir, quiet=True)
                nltk.download("omw-1.4", download_dir=nltk_data_dir, quiet=True)
                wordnet.synsets("car")
                self.wordnet_enabled = True
                logger.info("NLTK WordNet downloaded and initialized successfully.")
        except Exception as e:
            logger.warning("NLTK WordNet initialization failed. Falling back to static dictionary query expansion.", error=str(e))

    def parse(self, query: str) -> ParsedQuery:
        """Parses natural language query into structural components."""
        if not query:
            return ParsedQuery(raw_query="")

        raw_query = query.strip()
        parsed = ParsedQuery(raw_query=raw_query)

        # 1. Parse Camera Filters (e.g., "camera:cam_1", "cam:cam_2", "on camera camera_1")
        # Pattern matching cam:XXX or camera:XXX
        cam_matches = re.findall(r"\b(?:cam|camera):([\w\-]+)", raw_query, re.IGNORECASE)
        for cam in cam_matches:
            parsed.camera_ids.append(cam)
        # Remove camera syntax from clean query text, including optional "on" prefix
        clean_text = re.sub(r"\b(?:on\s+)?(?:cam|camera):[\w\-]+", "", raw_query, flags=re.IGNORECASE)

        # 2. Parse Spatial Zone (e.g., "in Zone A", "in zone:A", "zone:perimeter_2")
        zone_match = re.search(r"\bzone:([\w\-]+)", clean_text, re.IGNORECASE)
        if zone_match:
            parsed.spatial_zone = zone_match.group(1)
            clean_text = re.sub(r"\bzone:[\w\-]+", "", clean_text, flags=re.IGNORECASE)
        else:
            # Alternate match: "in Zone A" or "in zone A"
            zone_text_match = re.search(r"\bin zone\s+([\w\-]+)", clean_text, re.IGNORECASE)
            if zone_text_match:
                parsed.spatial_zone = zone_text_match.group(1)
                clean_text = re.sub(r"\bin zone\s+[\w\-]+", "", clean_text, flags=re.IGNORECASE)

        # 3. Parse Negatives / Exclusions (e.g., "but NOT trucks", "except vans", "no cars")
        # Match patterns like: "but not X", "except X", "no X"
        not_matches = re.findall(r"\b(?:but\s+)?not\s+(\w+s?)", clean_text, re.IGNORECASE)
        except_matches = re.findall(r"\bexcept\s+(\w+s?)", clean_text, re.IGNORECASE)
        no_matches = re.findall(r"\bno\s+(\w+s?)", clean_text, re.IGNORECASE)
        
        exclusions = set()
        for word in not_matches + except_matches + no_matches:
            cls = self._normalize_class(word)
            if cls:
                exclusions.add(cls)
                
        parsed.excluded_classes = list(exclusions)

        # Remove negative phrases from semantic text query
        clean_text = re.sub(r"\b(?:but\s+)?not\s+\w+s?", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\bexcept\s+\w+s?", "", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"\bno\s+\w+s?", "", clean_text, flags=re.IGNORECASE)

        # 4. Parse Time Range Windows
        now_ms = int(time.time() * 1000)
        time_parsed = False
        
        # Pattern "last X hours/h"
        hour_match = re.search(r"\blast\s+(\d+)\s*(?:hours?|h)\b", clean_text, re.IGNORECASE)
        if hour_match:
            hours = int(hour_match.group(1))
            parsed.start_time = now_ms - (hours * 3600 * 1000)
            parsed.end_time = now_ms
            clean_text = re.sub(r"\blast\s+\d+\s*(?:hours?|h)\b", "", clean_text, flags=re.IGNORECASE)
            time_parsed = True

        # Pattern "last X mins/m"
        min_match = re.search(r"\blast\s+(\d+)\s*(?:minutes?|mins?|m)\b", clean_text, re.IGNORECASE)
        if min_match and not time_parsed:
            minutes = int(min_match.group(1))
            parsed.start_time = now_ms - (minutes * 60 * 1000)
            parsed.end_time = now_ms
            clean_text = re.sub(r"\blast\s+\d+\s*(?:minutes?|mins?|m)\b", "", clean_text, flags=re.IGNORECASE)
            time_parsed = True

        # Pattern "today"
        if re.search(r"\btoday\b", clean_text, re.IGNORECASE) and not time_parsed:
            # Start of today (UTC or local simple day start)
            import datetime
            today_start = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
            parsed.start_time = int(today_start.timestamp() * 1000)
            parsed.end_time = now_ms
            clean_text = re.sub(r"\btoday\b", "", clean_text, flags=re.IGNORECASE)
            time_parsed = True

        # Pattern "yesterday"
        if re.search(r"\byesterday\b", clean_text, re.IGNORECASE) and not time_parsed:
            import datetime
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            yesterday_start = datetime.datetime.combine(yesterday, datetime.time.min)
            yesterday_end = datetime.datetime.combine(yesterday, datetime.time.max)
            parsed.start_time = int(yesterday_start.timestamp() * 1000)
            parsed.end_time = int(yesterday_end.timestamp() * 1000)
            clean_text = re.sub(r"\byesterday\b", "", clean_text, flags=re.IGNORECASE)
            time_parsed = True

        # 5. Extract positive classes
        # Clean extra spaces and symbols
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        words = re.findall(r"\b\w+\b", clean_text.lower())
        
        pos_classes = set()
        for w in words:
            cls = self._normalize_class(w)
            if cls and cls not in exclusions:
                pos_classes.add(cls)
        parsed.classes = list(pos_classes)

        # 6. Query expansion via WordNet or static synonym dictionary
        synonyms = set()
        for w in parsed.classes:
            syns = self.get_synonyms(w)
            for s in syns:
                if s != w:
                    synonyms.add(s)
        parsed.expanded_synonyms = list(synonyms)

        # Set final clean semantic text query
        parsed.semantic_query = clean_text

        return parsed

    def _normalize_class(self, word: str) -> Optional[str]:
        """Normalizes plural terms and checks if the word matches a surveillance class."""
        word = word.lower()
        # Simple plural removal
        singular = word[:-1] if word.endswith("s") and len(word) > 1 else word
        
        if word in SURVEILLANCE_CLASSES:
            return word
        if singular in SURVEILLANCE_CLASSES:
            return singular
            
        # Map common plurals or synonyms to base classes
        mappings = {
            "people": "person",
            "pedestrians": "person",
            "autos": "car",
            "cars": "car",
            "vans": "vehicle",
            "trucks": "truck",
            "backpacks": "backpack",
            "bags": "luggage",
        }
        return mappings.get(word) or mappings.get(singular)

    def get_synonyms(self, word: str) -> List[str]:
        """Returns synonyms for the given word from WordNet or fallback static dictionary."""
        word = word.lower()
        synonyms = set()

        if self.wordnet_enabled:
            try:
                from nltk.corpus import wordnet
                for syn in wordnet.synsets(word):
                    for lemma in syn.lemmas():
                        name = lemma.name().lower().replace("_", " ").replace("-", " ")
                        # Exclude compound terms unless they match surveillance classes
                        if " " not in name and name in SURVEILLANCE_CLASSES:
                            synonyms.add(name)
            except Exception as e:
                logger.warning("Error fetching from WordNet. Using fallback dictionary.", error=str(e))

        # Merge in fallback terms to ensure core classes are covered
        if word in SYNONYM_FALLBACK:
            for s in SYNONYM_FALLBACK[word]:
                synonyms.add(s)

        # If WordNet returned nothing, check singular/plural mappings in fallback
        singular = word[:-1] if word.endswith("s") and len(word) > 1 else word
        if singular in SYNONYM_FALLBACK:
            for s in SYNONYM_FALLBACK[singular]:
                synonyms.add(s)

        return list(synonyms)
