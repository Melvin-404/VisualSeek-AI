# Index type and search parameter configurations for Milvus vector fields

# Distance metric for vector similarity (COSINE is standard for CLIP embeddings)
METRIC_TYPE = "COSINE"

# Approximate Nearest Neighbor (ANN) index algorithm
INDEX_TYPE = "HNSW"

# HNSW Index construction parameters
INDEX_PARAMS = {
    "metric_type": METRIC_TYPE,
    "index_type": INDEX_TYPE,
    "params": {
        "M": 16,              # Max connection edges per node (range: 4 to 64)
        "efConstruction": 256 # Candidate list size for graph building (range: 8 to 512)
    }
}

# HNSW Runtime search parameters
SEARCH_PARAMS = {
    "metric_type": METRIC_TYPE,
    "params": {
        "ef": 64              # Candidate list size for query traversal (range: 8 to 512)
    }
}
