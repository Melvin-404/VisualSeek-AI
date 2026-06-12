from pymilvus import Collection, utility
from vector_store.collections import (
    build_frame_embeddings_schema,
    build_object_embeddings_schema,
    build_event_embeddings_schema
)
from vector_store.indexes import INDEX_PARAMS

MIGRATION_ID = "0001_initial"


def up(env: str, ttl_seconds: int = 2592000) -> None:
    """Creates initial collections, applies HNSW indexes, and maps aliases.
    
    Args:
        env: Active environment prefix (e.g. dev, staging, prod)
        ttl_seconds: Collection-level TTL duration in seconds (defaults to 30 days)
    """
    print(f"Applying migration {MIGRATION_ID} for environment: {env}")

    # Define versioned names
    frame_coll_name = f"{env}_frame_embeddings_v1"
    object_coll_name = f"{env}_object_embeddings_v1"
    event_coll_name = f"{env}_event_embeddings_v1"

    # Define schemas
    frame_schema = build_frame_embeddings_schema()
    object_schema = build_object_embeddings_schema()
    event_schema = build_event_embeddings_schema()

    # Define collection properties (e.g. TTL)
    properties = {"collection.ttl.seconds": ttl_seconds} if ttl_seconds > 0 else None

    # Create Collections
    print(f"Creating collections: {frame_coll_name}, {object_coll_name}, {event_coll_name}...")
    c_frame = Collection(name=frame_coll_name, schema=frame_schema, properties=properties)
    c_object = Collection(name=object_coll_name, schema=object_schema, properties=properties)
    c_event = Collection(name=event_coll_name, schema=event_schema, properties=properties)

    # Create HNSW Indexes
    print("Creating HNSW indexes on 'embedding' fields...")
    c_frame.create_index(field_name="embedding", index_params=INDEX_PARAMS)
    c_object.create_index(field_name="embedding", index_params=INDEX_PARAMS)
    c_event.create_index(field_name="embedding", index_params=INDEX_PARAMS)

    # Assign/Swap Aliases
    # Note: Swap from old collection to new collection dynamically
    for base_name, versioned_name in [
        ("frame_embeddings", frame_coll_name),
        ("object_embeddings", object_coll_name),
        ("event_embeddings", event_coll_name)
    ]:
        alias_name = f"{env}_{base_name}"
        try:
            utility.create_alias(collection_name=versioned_name, alias=alias_name)
            print(f"Created alias '{alias_name}' -> '{versioned_name}'")
        except Exception:
            print(f"Alias '{alias_name}' already exists. Swapping to '{versioned_name}'...")
            try:
                utility.alter_alias(collection_name=versioned_name, alias=alias_name)
            except Exception as e:
                print(f"Alter failed: {e}. Dropping and recreating alias '{alias_name}'...")
                try:
                    utility.drop_alias(alias=alias_name)
                except Exception:
                    pass
                utility.create_alias(collection_name=versioned_name, alias=alias_name)


    print(f"Migration {MIGRATION_ID} completed successfully.")


def down(env: str) -> None:
    """Rolls back the initial collections and drops aliases.
    
    Args:
        env: Active environment prefix
    """
    print(f"Rolling back migration {MIGRATION_ID} for environment: {env}")

    # Drop aliases first
    for base_name in ["frame_embeddings", "object_embeddings", "event_embeddings"]:
        alias_name = f"{env}_{base_name}"
        try:
            utility.drop_alias(alias=alias_name)
            print(f"Dropped alias '{alias_name}'")
        except Exception:
            pass

    # Drop collections
    for suffix in ["frame_embeddings_v1", "object_embeddings_v1", "event_embeddings_v1"]:
        coll_name = f"{env}_{suffix}"
        if utility.has_collection(coll_name):
            print(f"Dropping collection '{coll_name}'...")
            utility.drop_collection(coll_name)

    print(f"Migration {MIGRATION_ID} rollback completed.")

