"""Real-time event publisher with Redis/WebSocket integration and PII redaction."""

import json
import logging
from typing import Dict, List, Optional

from events.base_detector import Event

logger = logging.getLogger(__name__)

# Redis import check
try:
    import redis
    HAS_REDIS = True
except ImportError:
    redis = None
    HAS_REDIS = False


class EventPublisher:
    """Handles WebSocket/Redis PubSub event distribution with strict GDPR PII redaction."""

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize publisher connections."""
        self.redis_client = None
        self.websocket_subscribers: List[callable] = []

        if redis_url and HAS_REDIS:
            try:
                self.redis_client = redis.from_url(redis_url)
                logger.info("Connected to Redis PubSub at %s", redis_url)
            except Exception as e:
                logger.warning("Failed to connect to Redis for event publishing: %s", e)

    def subscribe_websocket(self, callback: callable) -> None:
        """Register a callback function representing a WebSocket subscriber."""
        self.websocket_subscribers.append(callback)
        logger.debug("Registered new WebSocket subscriber. Total: %d", len(self.websocket_subscribers))

    def _redact_pii(self, metadata: dict) -> dict:
        """Redact sensitive PII (Person Identifiable Information) keys for GDPR compliance."""
        redacted = metadata.copy()
        
        # Keys that are forbidden in event payloads
        pii_forbidden_keys = {
            "name", "identity", "biometric", "face_embedding", "person_name", 
            "social_security", "driver_license", "gender", "age"
        }

        # Recursively redact forbidden keys
        for key in list(redacted.keys()):
            if any(forbidden in key.lower() for forbidden in pii_forbidden_keys):
                del redacted[key]
            elif isinstance(redacted[key], dict):
                redacted[key] = self._redact_pii(redacted[key])

        return redacted

    def publish(self, event: Event) -> dict:
        """Sanitize, redact PII, and publish the event payload to Redis and WebSockets.

        Returns:
            The sanitized and published JSON-serializable dictionary.
        """
        # Redact metadata PII
        sanitized_metadata = self._redact_pii(event.metadata)

        payload = {
            "event_id": event.event_id,
            "camera_id": event.camera_id,
            "event_type": event.event_type,
            "severity": event.severity,
            "timestamp_ms": event.timestamp_ms,
            "zone_id": event.zone_id,
            "metadata": sanitized_metadata,
        }

        payload_json = json.dumps(payload)

        # 1. Publish to Redis PubSub channel 'vision_query_events'
        if self.redis_client is not None:
            try:
                self.redis_client.publish("vision_query_events", payload_json)
            except Exception as e:
                logger.error("Failed to publish event to Redis: %s", e)

        # 2. Emit to registered WebSocket callbacks
        for callback in self.websocket_subscribers:
            try:
                callback(payload_json)
            except Exception as e:
                logger.warning("WebSocket emission callback error: %s", e)

        logger.info(
            "Emitted event %s (Type: %s, Severity: %s, Camera: %s)",
            event.event_id,
            event.event_type,
            event.severity,
            event.camera_id,
        )

        return payload
