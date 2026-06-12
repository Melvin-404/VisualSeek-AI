import os
import sys
import argparse
from pymilvus import connections, utility, Collection

# Add parent directory of vector_store to sys.path to support dynamic imports
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


def check_health(host: str, port: str, env: str) -> bool:
    """Verifies Milvus availability, collection existence, and index states.
    
    Args:
        host: Milvus service hostname/IP
        port: Milvus service port
        env: Active environment prefix
        
    Returns:
        bool: True if health check passes, False otherwise.
    """
    print(f"Starting Milvus health check on {host}:{port} for environment: {env}")
    try:
        connections.connect(alias="default", host=host, port=port)
        print("[OK] Connected to Milvus Standalone.")
    except Exception as e:
        print(f"[FAIL] Connection to Milvus failed: {e}")
        return False

    expected_aliases = [
        f"{env}_frame_embeddings",
        f"{env}_object_embeddings",
        f"{env}_event_embeddings"
    ]
    
    all_ok = True
    for alias in expected_aliases:
        try:
            col = Collection(name=alias)
            print(f"[OK] Alias/Collection '{alias}' exists.")
            print(f"     -> Points to collection: '{col.name}'")
            
            # Check if index exists on the embedding field
            indexes = col.indexes
            embedding_indexed = False
            for idx in indexes:
                if idx.field_name == "embedding":
                    print(f"[OK] Index exists on '{alias}' (field: 'embedding', type: '{idx.params.get('index_type')}', params: {idx.params.get('params')})")
                    embedding_indexed = True
                    break
            if not embedding_indexed:
                print(f"[FAIL] No index found on 'embedding' field of '{alias}'")
                all_ok = False
        except Exception as e:
            print(f"[FAIL] Alias/Collection '{alias}' does NOT exist or failed to load: {e}")
            all_ok = False


    # Check RBAC (list users to confirm permission/role check works)
    try:
        users = utility.list_users(include_role_info=False)
        print(f"[OK] RBAC check: Successfully listed users: {users}")
    except Exception as e:
        print(f"[INFO] RBAC/User listing check (may fail if auth disabled/unconfigured): {e}")

    connections.disconnect("default")
    return all_ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Milvus Healthcheck Utility")
    parser.add_argument("--env", type=str, default="dev", help="Environment prefix")
    parser.add_argument("--host", type=str, default=os.getenv("MILVUS_HOST", "localhost"), help="Milvus host")
    parser.add_argument("--port", type=str, default=os.getenv("MILVUS_PORT", "19530"), help="Milvus port")
    args = parser.parse_args()

    success = check_health(args.host, args.port, args.env)
    if success:
        print("\n[SUCCESS] All Milvus health checks passed.")
        sys.exit(0)
    else:
        print("\n[FAILURE] Some Milvus health checks failed.")
        sys.exit(1)
