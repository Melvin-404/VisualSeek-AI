"""NLU Query Parser — Main pipeline orchestrator.

Assembles the full NL query processing pipeline:
1. Sanitization (PII removal, injection prevention)
2. Redis cache lookup
3. Local entity extraction (spaCy)
4. Temporal parsing
5. LLM intent extraction
6. Fallback to regex/CLIP on LLM failure
7. Cache store
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Optional

import structlog

from app.core.config import settings
from app.services.nl_query.entity_extractor import SpaCyEntityExtractor
from app.services.nl_query.intent import IntentExtractionError, IntentExtractor, SearchIntent
from app.services.nl_query.temporal_parser import TemporalParser

logger = structlog.get_logger("nl_query.parser")

# Regex patterns for PII scrubbing
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,5}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CREDIT_CARD_RE = re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b")

# SQL injection / prompt injection patterns
_INJECTION_PATTERNS = [
    re.compile(r"(?:--|;|'|\"|\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b|\bSELECT\b)", re.IGNORECASE),
    re.compile(r"\bignore\s+(?:above|previous)\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"\bsystem\s*:\s*", re.IGNORECASE),
]

# Cache TTL
_CACHE_TTL_SECONDS = 86400  # 24 hours


class NLUQueryParser:
    """Main entry point for natural language query processing.

    Usage:
        parser = NLUQueryParser()
        intent = await parser.parse("Find red cars in parking lot from last 2 hours")
    """

    def __init__(self):
        self._entity_extractor = SpaCyEntityExtractor()
        self._temporal_parser = TemporalParser()
        self._intent_extractor = IntentExtractor()
        self._redis = None
        self._init_redis()

    def _init_redis(self):
        """Attempt to connect to Redis for query caching."""
        try:
            import redis

            self._redis = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            self._redis.ping()
            logger.info("Redis cache connected for NLU query caching.")
        except Exception as e:
            self._redis = None
            logger.warning(
                "Redis unavailable — NLU query caching disabled.",
                error=str(e),
            )

    async def parse(self, query: str) -> SearchIntent:
        """Parse a natural language query into a SearchIntent.

        Pipeline:
        1. Sanitize & validate input
        2. Check Redis cache
        3. Extract entities locally (spaCy / regex)
        4. Parse temporal expressions
        5. Call LLM for intent extraction
        6. On LLM failure → fall back to local regex parser
        7. Store result in Redis cache

        Returns:
            SearchIntent with populated fields.
        """
        start_time = time.monotonic()

        # 1. Sanitize
        sanitized = self._sanitize(query)
        if not sanitized:
            return SearchIntent(raw_query=query, rewritten_query=query)

        # 2. Cache lookup
        cache_key = self._cache_key(sanitized)
        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.info("NLU cache hit.", query=sanitized[:50])
            return cached

        # 3. Local entity extraction
        entities = self._entity_extractor.extract(sanitized)
        entity_context = entities.to_context_string()

        # 4. Temporal parsing
        time_range = self._temporal_parser.parse(sanitized)

        # 5. LLM intent extraction (with fallback)
        try:
            intent = await self._intent_extractor.extract(sanitized, entity_context)
        except IntentExtractionError as e:
            logger.warning(
                "LLM intent extraction failed. Falling back to local parser.",
                error=str(e),
            )
            intent = self._local_fallback(sanitized, entities)

        # Augment with temporal data if LLM didn't provide it
        if intent.time_range is None and time_range.start_ms is not None:
            intent.time_range = {
                "start_ms": time_range.start_ms,
                "end_ms": time_range.end_ms,
                "description": time_range.raw_expression,
            }

        # Ensure raw_query is set
        intent.raw_query = query

        # If rewritten_query is empty, use the sanitized query
        if not intent.rewritten_query:
            intent.rewritten_query = sanitized

        # 6. Cache store
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "NLU query parsed.",
            intent_type=intent.intent_type,
            object_class=intent.object_class,
            elapsed_ms=elapsed_ms,
            llm_cost=intent.llm_cost,
            fallback=intent.unstructured_fallback,
        )
        self._cache_set(cache_key, intent)

        return intent

    # --- Sanitization ---

    def _sanitize(self, query: str) -> str:
        """Remove PII, credentials, and injection attempts from query text."""
        text = query.strip()
        if not text:
            return ""

        # Max length guard
        if len(text) > 2000:
            text = text[:2000]
            logger.warning("Query truncated to 2000 chars.")

        # Remove PII — apply credit card BEFORE phone (credit card pattern is more specific)
        text = _CREDIT_CARD_RE.sub("[CARD]", text)
        text = _SSN_RE.sub("[SSN]", text)
        text = _PHONE_RE.sub("[PHONE]", text)
        text = _EMAIL_RE.sub("[EMAIL]", text)

        # Check for injection patterns
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning("Potential injection detected in query.", pattern=pattern.pattern)
                text = pattern.sub("", text)

        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    # --- Redis Caching ---

    def _cache_key(self, query: str) -> str:
        """Generate a deterministic cache key from query text."""
        normalized = query.lower().strip()
        h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return f"nlu:intent:{h}"

    def _cache_get(self, key: str) -> Optional[SearchIntent]:
        """Try to retrieve a cached SearchIntent from Redis."""
        if not self._redis:
            return None
        try:
            raw = self._redis.get(key)
            if raw:
                data = json.loads(raw)
                return SearchIntent(**data)
        except Exception as e:
            logger.debug("Redis cache get failed.", error=str(e))
        return None

    def _cache_set(self, key: str, intent: SearchIntent):
        """Store a SearchIntent in Redis with TTL."""
        if not self._redis:
            return
        try:
            self._redis.setex(
                key,
                _CACHE_TTL_SECONDS,
                json.dumps(intent.to_dict()),
            )
        except Exception as e:
            logger.debug("Redis cache set failed.", error=str(e))

    # --- Local Fallback Parser ---

    def _local_fallback(self, query: str, entities) -> SearchIntent:
        """Regex-based fallback when LLM is unavailable.

        Uses the locally extracted entities to build a basic SearchIntent
        and sets unstructured_fallback=True to signal the search engine
        to use CLIP text embedding for the full query.
        """
        intent = SearchIntent(
            raw_query=query,
            unstructured_fallback=True,
            rewritten_query=query,
        )

        # Determine primary object class
        if entities.object_classes:
            # Map common terms to canonical classes
            class_map = {
                "people": "person", "man": "person", "woman": "person",
                "child": "person", "kid": "person", "pedestrian": "person",
                "car": "car", "vehicle": "car", "truck": "truck",
                "bus": "bus", "bicycle": "bicycle", "motorcycle": "motorcycle",
                "dog": "dog", "cat": "cat", "bird": "bird", "animal": "animal",
            }
            for cls in entities.object_classes:
                mapped = class_map.get(cls, cls)
                intent.object_class = mapped
                break

        # Colors
        if entities.colors:
            intent.color = entities.colors[0]

        # Attributes from clothing + behaviors
        intent.attributes = entities.clothing + entities.behaviors

        # Vehicle types as attributes
        if entities.vehicle_types:
            intent.attributes.extend(entities.vehicle_types)
            if not intent.object_class:
                intent.object_class = "car"

        # Negation detection (simple regex)
        neg_matches = re.findall(
            r"\b(?:not|without|no|except|excluding)\s+([\w\s]+?)(?:\s+(?:in|on|at|from|near|cam|camera|zone|between|last|today|yesterday)|$)",
            query.lower(),
        )
        intent.negations = [n.strip() for n in neg_matches if n.strip()]

        # Camera IDs
        cam_matches = re.findall(r"\bcam(?:era)?[-_\s]?(\d+)\b", query.lower())
        intent.camera_ids = [f"cam-{c.zfill(3)}" for c in cam_matches]

        # Spatial zone (basic)
        zone_match = re.search(
            r"\b(?:in|near|at)\s+(?:the\s+)?((?:parking\s+lot|loading\s+dock|lobby|corridor|warehouse|server\s+room|rooftop|emergency\s+exit|zone\s+\w+)(?:\s+\w)?)",
            query.lower(),
        )
        if zone_match:
            intent.spatial_zone = zone_match.group(1).strip()

        # Intent classification heuristics
        count_words = {"how many", "count", "number of", "total", "average"}
        compare_words = {"which camera", "compare", "busiest", "most", "least"}
        event_words = {"loitering", "fighting", "intrusion", "falling", "abandoned", "tailgating"}

        query_lower = query.lower()
        if any(w in query_lower for w in count_words):
            intent.intent_type = "statistical_query"
        elif any(w in query_lower for w in compare_words):
            intent.intent_type = "comparison"
        elif any(w in query_lower for w in event_words):
            intent.intent_type = "event_search"
            for evt in event_words:
                if evt in query_lower:
                    intent.event_type = evt
                    break
        else:
            intent.intent_type = "object_search"

        return intent
