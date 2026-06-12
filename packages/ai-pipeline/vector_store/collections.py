from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pymilvus import FieldSchema, CollectionSchema, DataType

# Vector store settings
VECTOR_DIM = 512

@dataclass
class FrameEmbedding:
    """Dataclass representing a frame embedding record."""
    id: str
    camera_id: str
    segment_id: str
    frame_number: int
    timestamp_ms: int
    embedding: List[float]
    object_classes: List[str] = field(default_factory=list)
    raw_labels: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ObjectEmbedding:
    """Dataclass representing an object embedding record."""
    id: str
    track_id: int
    class_label: str
    embedding: List[float]
    first_seen: int
    last_seen: int
    camera_id: str


@dataclass
class EventEmbedding:
    """Dataclass representing an event semantic embedding record."""
    id: str
    event_id: str
    event_type: str
    severity: str
    start_time: int
    end_time: int
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)


def build_frame_embeddings_schema(description: str = "VisionQuery Frame Embeddings Collection") -> CollectionSchema:
    """Builds the pymilvus CollectionSchema for frame embeddings."""
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=36, is_primary=True, auto_id=False, description="Frame UUID"),
        FieldSchema(name="camera_id", dtype=DataType.VARCHAR, max_length=36, is_partition_key=True, description="Camera UUID"),
        FieldSchema(name="segment_id", dtype=DataType.VARCHAR, max_length=36, description="Segment UUID"),
        FieldSchema(name="frame_number", dtype=DataType.INT64, description="Frame Index"),
        FieldSchema(name="timestamp_ms", dtype=DataType.INT64, description="Timestamp offset in MS"),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=VECTOR_DIM, description="CLIP Vector Embedding"),
        FieldSchema(name="object_classes", dtype=DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=100, max_length=100, description="Detected classes"),
        FieldSchema(name="raw_labels", dtype=DataType.JSON, description="Detailed labels JSON")
    ]
    return CollectionSchema(fields=fields, description=description, enable_dynamic_field=False)


def build_object_embeddings_schema(description: str = "VisionQuery Object Embeddings Collection") -> CollectionSchema:
    """Builds the pymilvus CollectionSchema for object embeddings."""
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=36, is_primary=True, auto_id=False, description="Object UUID"),
        FieldSchema(name="track_id", dtype=DataType.INT64, description="Object Track ID"),
        FieldSchema(name="class_label", dtype=DataType.VARCHAR, max_length=100, description="Class label"),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=VECTOR_DIM, description="Inference Vector Embedding"),
        FieldSchema(name="first_seen", dtype=DataType.INT64, description="Appearance start timestamp MS"),
        FieldSchema(name="last_seen", dtype=DataType.INT64, description="Appearance end timestamp MS"),
        FieldSchema(name="camera_id", dtype=DataType.VARCHAR, max_length=36, is_partition_key=True, description="Camera UUID")
    ]
    return CollectionSchema(fields=fields, description=description, enable_dynamic_field=False)


def build_event_embeddings_schema(description: str = "VisionQuery Event Embeddings Collection") -> CollectionSchema:
    """Builds the pymilvus CollectionSchema for event semantic embeddings."""
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=36, is_primary=True, auto_id=False, description="Event Embedding UUID"),
        FieldSchema(name="event_id", dtype=DataType.VARCHAR, max_length=36, description="Database Event UUID"),
        FieldSchema(name="event_type", dtype=DataType.VARCHAR, max_length=100, description="Event category"),
        FieldSchema(name="severity", dtype=DataType.VARCHAR, max_length=50, description="Event severity"),
        FieldSchema(name="start_time", dtype=DataType.INT64, description="Start timestamp MS"),
        FieldSchema(name="end_time", dtype=DataType.INT64, description="End timestamp MS"),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=VECTOR_DIM, description="Semantic Event Embedding"),
        FieldSchema(name="metadata", dtype=DataType.JSON, description="Event metadata JSON")
    ]
    return CollectionSchema(fields=fields, description=description, enable_dynamic_field=False)
