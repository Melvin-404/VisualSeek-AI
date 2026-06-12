import os
import sys
import uuid
import time
import random
import pytest
from pymilvus import connections, utility, Collection

# Add parent directory of vector_store to sys.path to support dynamic imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from vector_store.migrations import runner
from vector_store.collections import VECTOR_DIM


@pytest.fixture(scope="module")
def milvus_connection():
    """Fixture to connect to Milvus Standalone for the duration of the test module."""
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    connections.connect(alias="default", host=host, port=port)
    yield
    connections.disconnect("default")


@pytest.fixture(scope="module")
def test_environment(milvus_connection):
    """Fixture to bootstrap the 'test' Milvus environment and clean up afterwards."""
    env = "test_env"
    
    # Clean up any leftover test collections/aliases first
    runner.run_migration_action("0001_initial", "down", env=env)
    
    # Run migration UP
    # We set TTL to 0 (disabled) or a short duration for the test environment
    runner.run_migration_action("0001_initial", "up", env=env, ttl_seconds=0)
    
    yield env
    
    # Run migration DOWN (cleanup)
    runner.run_migration_action("0001_initial", "down", env=env)


def test_migration_and_collections_created(test_environment):
    """Asserts that the test environment aliases are successfully registered and point to collections."""
    env = test_environment
    expected_aliases = [
        f"{env}_frame_embeddings",
        f"{env}_object_embeddings",
        f"{env}_event_embeddings"
    ]
    for alias in expected_aliases:
        col = Collection(name=alias)
        assert col is not None



def test_vector_indexing_and_recall_performance(test_environment):
    """Inserts 1,000 vectors, flushes, loads, and asserts search recall@10 > 0.95 and latency < 50ms."""
    env = test_environment
    alias_name = f"{env}_frame_embeddings"
    
    col = Collection(name=alias_name)
    
    # 1. Generate 1000 records
    num_records = 1000
    camera_ids = [str(uuid.uuid4()) for _ in range(5)] # 5 cameras
    
    records = []
    inserted_ids = []
    inserted_vectors = []
    
    for i in range(num_records):
        rec_id = str(uuid.uuid4())
        cam_id = camera_ids[i % 5]
        # Generate random normalized 512-dim vector for Cosine metric
        vec = [random.uniform(-1.0, 1.0) for _ in range(VECTOR_DIM)]
        # Normalize vector to unit length (improves cosine similarity matching stability)
        norm = sum(x**2 for x in vec)**0.5
        vec = [x / norm for x in vec]
        
        records.append({
            "id": rec_id,
            "camera_id": cam_id,
            "segment_id": str(uuid.uuid4()),
            "frame_number": i,
            "timestamp_ms": i * 100,
            "embedding": vec,
            "object_classes": ["car", "person"] if i % 2 == 0 else ["truck"],
            "raw_labels": {"detections": [{"confidence": 0.9, "label": "car"}]}
        })
        
        inserted_ids.append(rec_id)
        inserted_vectors.append((rec_id, cam_id, vec))

    # 2. Insert records
    # PyMilvus ORM insert expects list of dictionaries
    print(f"\nInserting {num_records} frame records into {alias_name}...")
    col.insert(records)
    
    # Flush data to disk to seal segments and build indexes
    print("Flushing data...")
    col.flush()
    
    # Load collection into query node memory
    print("Loading collection...")
    col.load()
    
    # 3. Test Search Latency & Recall
    # We select 50 random inserted vectors to query
    test_queries = random.sample(inserted_vectors, 50)
    
    latency_records = []
    recall_hits = 0
    
    search_params = {
        "metric_type": "COSINE",
        "params": {"ef": 64}
    }
    
    for rec_id, cam_id, vec in test_queries:
        # Measure search latency
        t_start = time.perf_counter()
        # Search using the partition key (camera_id) for isolation
        results = col.search(
            data=[vec],
            anns_field="embedding",
            param=search_params,
            limit=10,
            expr=f"camera_id == '{cam_id}'"
        )
        t_end = time.perf_counter()
        
        latency_ms = (t_end - t_start) * 1000
        latency_records.append(latency_ms)
        
        # Verify recall@10 (original rec_id should be in top 10 results)
        if results and len(results) > 0:
            hits = [hit.id for hit in results[0]]
            if rec_id in hits:
                recall_hits += 1

    avg_latency = sum(latency_records) / len(latency_records)
    p95_latency = sorted(latency_records)[int(len(latency_records) * 0.95)]
    recall_rate = recall_hits / len(test_queries)
    
    print(f"\nSearch metrics:")
    print(f" - Average Latency: {avg_latency:.2f} ms")
    print(f" - 95th Percentile Latency: {p95_latency:.2f} ms")
    print(f" - Recall@10 Rate: {recall_rate * 100:.2f}%")
    
    # Assert recall criteria (> 0.95)
    assert recall_rate > 0.95, f"Recall rate was {recall_rate}, expected > 0.95"
    
    # Assert latency criteria (sub-50ms)
    assert avg_latency < 50.0, f"Average latency was {avg_latency} ms, expected < 50ms"
    assert p95_latency < 50.0, f"95th percentile latency was {p95_latency} ms, expected < 50ms"


def test_alias_swapping(test_environment):
    """Verifies that we can swap an alias to a different collection version dynamically."""
    env = test_environment
    base_name = "frame_embeddings"
    alias_name = f"{env}_{base_name}"
    
    v1_collection = f"{alias_name}_v1"
    v2_collection = f"{alias_name}_v2"
    
    # Create a dummy collection representing version 2
    from vector_store.collections import build_frame_embeddings_schema
    schema = build_frame_embeddings_schema(description="V2 Collection")
    
    if utility.has_collection(v2_collection):
        utility.drop_collection(v2_collection)
        
    c_v2 = Collection(name=v2_collection, schema=schema)
    
    # Verify current alias points to v1
    v1_aliases = utility.list_aliases(v1_collection)
    assert alias_name in v1_aliases
    
    # Swap alias to v2
    utility.alter_alias(collection_name=v2_collection, alias=alias_name)
    
    # Verify alias now points to v2
    v1_aliases_after = utility.list_aliases(v1_collection)
    v2_aliases_after = utility.list_aliases(v2_collection)
    assert alias_name not in v1_aliases_after
    assert alias_name in v2_aliases_after
    
    # Clean up v2
    utility.alter_alias(collection_name=v1_collection, alias=alias_name)
    utility.drop_collection(v2_collection)
