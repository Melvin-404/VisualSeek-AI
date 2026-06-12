import os
import sys
import time
import uuid
import base64
import asyncio
import pytest
from pymilvus import connections, Collection, utility
from shapely.geometry import Polygon

# Ensure we can import modules from both apps/api/app and packages/ai-pipeline/src
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ai_pipeline_src = os.path.join(root_dir, "packages", "ai-pipeline", "src")
if ai_pipeline_src not in sys.path:
    sys.path.insert(0, ai_pipeline_src)

from vector_store.migrations import runner
from vector_store.collections import VECTOR_DIM
from app.services.vector_search import VectorSearchService
from app.services.query_parser import QueryParser
from app.services.reranker import Reranker
from app.services.search_cache import SearchCache


@pytest.fixture(autouse=True)
def mock_text_embedding_mapping(monkeypatch):
    """Automatically patch VectorSearchService's text_embedder with a smart deterministic matcher."""
    import numpy as np
    
    class SmartMockTextEmbedder:
        def embed_text(self, text: str):
            text_lower = text.lower()
            concept = "car"
            if "truck" in text_lower:
                concept = "truck"
            elif "pedestrian" in text_lower or "person" in text_lower or "jacket" in text_lower:
                concept = "pedestrian"
            elif "suv" in text_lower:
                concept = "suv"
            
            vec = _generate_fixed_vector(concept)
            return np.array(vec, dtype=np.float32), "mock-clip-vit-b-32", 0.1

    # Override the init of VectorSearchService
    original_init = VectorSearchService.__init__
    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.text_embedder = SmartMockTextEmbedder()
        
    monkeypatch.setattr(VectorSearchService, "__init__", patched_init)


@pytest.fixture(scope="module")
def bootstrap_milvus_search_env():
    """Bootstraps a dedicated test environment in Milvus, seeding mock frame embeddings."""
    env = "test_search_env"
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    
    # Establish connection
    connections.connect(alias="default", host=host, port=port)
    
    # Clean down and up
    runner.run_migration_action("0001_initial", "down", env=env)
    runner.run_migration_action("0001_initial", "up", env=env, ttl_seconds=0)
    
    # Insert seed data
    col = Collection(name=f"{env}_frame_embeddings")
    
    records = []
    # Seed 10 distinct records with predefined semantics
    # Record 0: red car on cam_1 inside zone_a
    records.append({
        "id": str(uuid.uuid4()),
        "camera_id": "cam_1",
        "segment_id": str(uuid.uuid4()),
        "frame_number": 0,
        "timestamp_ms": 1000,
        "embedding": _generate_fixed_vector("car"),
        "object_classes": ["car", "vehicle"],
        "raw_labels": {
            "detections": [{"label": "car", "confidence": 0.9, "bbox": [0.1, 0.1, 0.3, 0.3]}],
            "description": "a bright red car parked next to the curb"
        }
    })
    
    # Record 1: blue truck on cam_1 outside zone_a
    records.append({
        "id": str(uuid.uuid4()),
        "camera_id": "cam_1",
        "segment_id": str(uuid.uuid4()),
        "frame_number": 1,
        "timestamp_ms": 2000,
        "embedding": _generate_fixed_vector("truck"),
        "object_classes": ["truck", "vehicle"],
        "raw_labels": {
            "detections": [{"label": "truck", "confidence": 0.85, "bbox": [0.6, 0.6, 0.9, 0.9]}],
            "description": "a heavy duty blue truck driving down the highway"
        }
    })
    
    # Record 2: pedestrian/person walking on cam_2 inside zone_a
    records.append({
        "id": str(uuid.uuid4()),
        "camera_id": "cam_2",
        "segment_id": str(uuid.uuid4()),
        "frame_number": 2,
        "timestamp_ms": 3000,
        "embedding": _generate_fixed_vector("pedestrian"),
        "object_classes": ["person"],
        "raw_labels": {
            "detections": [{"label": "person", "confidence": 0.95, "bbox": [0.2, 0.2, 0.4, 0.4]}],
            "description": "a pedestrian wearing a black jacket walking past"
        }
    })
    
    # Record 3: red suv/car on cam_2 outside zone_a
    records.append({
        "id": str(uuid.uuid4()),
        "camera_id": "cam_2",
        "segment_id": str(uuid.uuid4()),
        "frame_number": 3,
        "timestamp_ms": 4000,
        "embedding": _generate_fixed_vector("suv"),
        "object_classes": ["car", "vehicle"],
        "raw_labels": {
            "detections": [{"label": "car", "confidence": 0.88, "bbox": [0.7, 0.7, 0.9, 0.9]}],
            "description": "a red suv turning at the intersection"
        }
    })

    col.insert(records)
    col.flush()
    col.load()
    
    yield env
    
    runner.run_migration_action("0001_initial", "down", env=env)
    connections.disconnect("default")


def _generate_fixed_vector(val) -> list:
    """Helper to generate a deterministic unit vector for testing."""
    import hashlib
    import numpy as np
    hasher = hashlib.sha256()
    hasher.update(str(val).encode("utf-8"))
    seed = int(hasher.hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(VECTOR_DIM).astype(np.float32)
    norm = np.linalg.norm(vec)
    return (vec / max(norm, 1e-6)).tolist()


def test_connection_pooling():
    """Asserts that the connection pool correctly leases and releases connection aliases."""
    service = VectorSearchService()
    
    alias_1 = service.lease_connection()
    alias_2 = service.lease_connection()
    
    assert alias_1 != alias_2
    assert alias_1.startswith("pool_conn_")
    assert alias_2.startswith("pool_conn_")
    
    # Return to pool
    service.release_connection(alias_1)
    service.release_connection(alias_2)
    
    # Check that we can lease a connection alias successfully
    alias_3 = service.lease_connection()
    assert alias_3.startswith("pool_conn_")
    service.release_connection(alias_3)


def test_query_parsing_and_expansion():
    """Asserts that natural language queries are parsed into structured filters and expanded via synonyms."""
    parser = QueryParser()
    
    # Test query with negative classes, camera and time window
    query = "red cars on camera:cam_1 today but NOT trucks"
    parsed = parser.parse(query)
    
    assert parsed.semantic_query == "red cars"
    assert "car" in parsed.classes
    assert "truck" in parsed.excluded_classes
    assert "cam_1" in parsed.camera_ids
    assert parsed.start_time is not None
    assert parsed.end_time is not None
    
    # Synonym check (WordNet or static dictionary)
    assert any(syn in parsed.expanded_synonyms for syn in ["vehicle", "automobile", "motorcar", "sedan", "suv"])


@pytest.mark.asyncio
async def test_semantic_and_hybrid_search(bootstrap_milvus_search_env):
    """Verifies that we retrieve correct seeded records based on vector match and metadata filters."""
    env = bootstrap_milvus_search_env
    service = VectorSearchService()
    
    # Search for cars on camera cam_1
    res = await service.search(
        query_text="red cars on camera:cam_1",
        collection_name=f"{env}_frame_embeddings"
    )
    
    assert res["count"] > 0
    # Top result should be the red car from cam_1
    top_hit = res["results"][0]
    assert top_hit["camera_id"] == "cam_1"
    assert "car" in top_hit["object_classes"]


@pytest.mark.asyncio
async def test_negative_search_filtering(bootstrap_milvus_search_env):
    """Asserts that negative search modifiers exclude specified categories from output."""
    env = bootstrap_milvus_search_env
    service = VectorSearchService()
    
    # Search for vehicles but NOT trucks on cam_1
    res = await service.search(
        query_text="vehicles on camera:cam_1 no trucks",
        collection_name=f"{env}_frame_embeddings"
    )
    
    # We seeded a car and a truck on cam_1. The truck should be filtered out, leaving only the car.
    assert res["count"] == 1
    hit = res["results"][0]
    assert "car" in hit["object_classes"]
    assert "truck" not in hit["object_classes"]


@pytest.mark.asyncio
async def test_spatial_zone_filtering(bootstrap_milvus_search_env):
    """Verifies that spatial search filters out frame detections falling outside the virtual polygon boundary."""
    env = bootstrap_milvus_search_env
    service = VectorSearchService()
    
    # Search for vehicles in zone_a
    # zone_a covers [0.0, 0.0] to [0.5, 0.5]
    # Record 0 (car): bbox center is [0.2, 0.2] -> inside zone_a
    # Record 1 (truck): bbox center is [0.75, 0.75] -> outside zone_a
    res = await service.search(
        query_text="vehicles in zone:zone_a",
        collection_name=f"{env}_frame_embeddings"
    )
    
    # Only the car is in zone_a
    assert res["count"] == 1
    assert "car" in res["results"][0]["object_classes"]


@pytest.mark.asyncio
async def test_cross_encoder_reranking(bootstrap_milvus_search_env):
    """Verifies that Cross-Encoder re-ranks candidate results to surface the textually closer match."""
    env = bootstrap_milvus_search_env
    service = VectorSearchService()
    
    # Query: "red SUV turning"
    # Milvus matches both red car (Rec 0) and red SUV (Rec 3).
    # Since Rec 3 has description containing "red suv turning", re-ranker should rank Rec 3 higher than Rec 0.
    res = await service.search(
        query_text="red SUV turning",
        collection_name=f"{env}_frame_embeddings"
    )
    
    assert res["count"] >= 2
    top_hit = res["results"][0]
    # Check description in raw_labels
    assert "suv" in top_hit["raw_labels"]["description"].lower()


@pytest.mark.asyncio
async def test_search_caching_redis(bootstrap_milvus_search_env):
    """Validates that search caching returns identical results instantly and logs cache status."""
    env = bootstrap_milvus_search_env
    service = VectorSearchService()
    
    # First query
    res1 = await service.search(
        query_text="pedestrian in black jacket",
        collection_name=f"{env}_frame_embeddings"
    )
    assert res1["cached"] is False
    
    # Second query (identical)
    res2 = await service.search(
        query_text="pedestrian in black jacket",
        collection_name=f"{env}_frame_embeddings"
    )
    assert res2["cached"] is True
    assert len(res2["results"]) == len(res1["results"])


@pytest.mark.asyncio
async def test_camera_access_control(bootstrap_milvus_search_env):
    """Asserts that queries only return results within the allowed camera list."""
    env = bootstrap_milvus_search_env
    service = VectorSearchService()
    
    # Search with permission only to cam_2
    res = await service.search(
        query_text="vehicles",
        collection_name=f"{env}_frame_embeddings",
        user_allowed_cameras=["cam_2"]
    )
    
    # All results must be from cam_2
    for hit in res["results"]:
        assert hit["camera_id"] == "cam_2"


@pytest.mark.asyncio
async def test_cursor_pagination(bootstrap_milvus_search_env):
    """Verifies cursor-based pagination steps and returns correct token cursor."""
    env = bootstrap_milvus_search_env
    service = VectorSearchService()
    
    # Query with limit 1
    res1 = await service.search(
        query_text="vehicles",
        collection_name=f"{env}_frame_embeddings",
        limit=1
    )
    
    assert len(res1["results"]) == 1
    cursor = res1["next_cursor"]
    assert cursor is not None
    
    # Next page query
    res2 = await service.search(
        query_text="vehicles",
        collection_name=f"{env}_frame_embeddings",
        limit=1,
        cursor=cursor
    )
    
    assert len(res2["results"]) == 1
    assert res2["results"][0]["id"] != res1["results"][0]["id"]


@pytest.mark.asyncio
async def test_federated_multi_instance_search(bootstrap_milvus_search_env):
    """Verifies that federated search merges results correctly from secondary instances."""
    env = bootstrap_milvus_search_env
    service = VectorSearchService()
    
    # Register mock secondary instance url
    service.federated_instances = ["localhost:19530"]
    
    res = service.federated_search(
        query_text="vehicles",
        collection_name=f"{env}_frame_embeddings",
        limit=2
    )
    
    assert res["federated"] is True
    assert len(res["results"]) > 0


@pytest.mark.asyncio
async def test_concurrency_stress(bootstrap_milvus_search_env):
    """Load test executing 100 concurrent search operations to check pool scaling and sub-100ms latency."""
    env = bootstrap_milvus_search_env
    service = VectorSearchService()
    
    # Benchmark 100 concurrent searches
    tasks = []
    for i in range(100):
        tasks.append(
            service.search(
                query_text=f"search task {i % 5}",
                collection_name=f"{env}_frame_embeddings",
                bypass_cache=True # Ensure it hits Milvus each time
            )
        )
        
    start_time = time.perf_counter()
    results = await asyncio.gather(*tasks)
    elapsed = (time.perf_counter() - start_time) * 1000.0
    avg_latency = elapsed / 100.0
    
    print(f"\nConcurrency Stress test:")
    print(f" - Completed 100 concurrent searches in {elapsed:.2f} ms")
    print(f" - Average latency per search: {avg_latency:.2f} ms")
    
    assert len(results) == 100
    # Average concurrent search should scale well under pooled connection aliases
    assert avg_latency < 100.0
