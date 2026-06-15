# VisionQuery AI Search Accuracy Gap Analysis

This report documents the baseline search accuracy of VisionQuery AI prior to the upgrade, performs a root cause failure analysis, and outlines the corresponding architectural upgrades to address these limitations.

## Executive Summary

Surveillance search performance was benchmarked using 30 natural language security queries across three main categories (Color, Attribute, and Temporal/Cross-Camera). The results show a significant gap between the current capability and the target 90%+ query accuracy:

| Query Category | Precision@1 | Precision@5 | MRR | Mean Latency | Status / Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Colour Queries** | 40.0% | 10.0% | 0.4000 | 27.38 ms | **Fails on real data** (successful only via mock fallback matching). |
| **Attribute Queries** | 60.0% | 14.0% | 0.6500 | 19.25 ms | **Fails on real data** (successful only via mock fallback matching). |
| **Temporal / Cross-Camera** | 0.0% | 0.0% | 0.0000 | 18.50 ms | **Complete Failure** (no correlation of identities across feeds). |

---

## Category Gap Analysis & Root Cause Failure Report

### 1. Colour Queries (e.g. "grey car", "red shirt")
* **Current Performance**: Precision@1 = 40.0%, Precision@5 = 10.0%, MRR = 0.4000
* **Root Cause of Failures**:
  * **No Storage**: Bounding box detections saved in PostgreSQL (`detected_objects`) contain only coordinates and raw class labels. Color attributes are never extracted or saved.
  * **No Pipeline Integration**: Although the live camera processing loop runs YOLOv11m tracking, it does not execute any color classification or feature extraction.
  * **Milvus Collection Schema Mismatch**: The backend API expects to query a collection called `frame_embeddings` in Milvus, but the local Milvus database contains versioned collections (e.g., `dev_frame_embeddings_v1`) without any alias mapping to the plain `frame_embeddings` name, causing connection exceptions and falling back to a mock static dataset.
* **Upgrades to Address (Phase 2 & 4)**:
  * **Phase 2.1**: Implement dominant HSV color extraction on cropped bounding boxes using center-weighted Gaussian masks to remove background noise, clustering using K-Means (K=3), and mapping to 12 human-readable color names.
  * **Phase 4.2**: Update search parser to extract color keywords and construct structured SQL `WHERE` queries filtering on `dominant_colour` indices in PostgreSQL.

### 2. Attribute Queries (e.g. "man with backpack", "person in safety vest")
* **Current Performance**: Precision@1 = 60.0%, Precision@5 = 14.0%, MRR = 0.6500
* **Root Cause of Failures**:
  * **No Metadata Extraction**: The surveillance pipeline doesn't perform zero-shot classification on objects. Attributes like "backpack", "safety vest", "laptop", or "helmet" are never saved in the database.
  * **Mock-Only Support**: The NLU query parser falls back to a mock keyword search when the Milvus query fails. Thus, the results only represent simulated data, and real-world feeds fail completely.
* **Upgrades to Address (Phase 2 & 4)**:
  * **Phase 2.2**: Integrate timm's `MobileNetV3-Large` classifier to categorize vehicle body styles (SUV, sedan, truck, van, motorcycle, bus) with dynamic batching.
  * **Phase 2.3**: Deploy pre-cached zero-shot OpenCLIP prompts for person attributes (carried items, clothing types, gender estimation) running in FP16 on GPU.
  * **Phase 4.2**: Implement GIN indexes on `carried_items` and structured query filters in the metadata search service.

### 3. Cross-Camera & Temporal Queries (e.g. "same person across Parking Lot A and lobby")
* **Current Performance**: Precision@1 = 0.0%, Precision@5 = 0.0%, MRR = 0.0000
* **Root Cause of Failures**:
  * **No ReID Embeddings**: Detections in different camera feeds use isolated local track IDs. There is no shared feature space or embedding representation to correlate objects across cameras.
  * **No Cross-Camera Gallery**: No gallery matching system exists to link sightings of the same individual/vehicle across camera boundaries or build location trajectories.
  * **No Query Parsing**: The query parser does not recognize temporal constructs ("between X and Y") or cross-camera requests ("same car").
* **Upgrades to Address (Phase 3, 4 & 5)**:
  * **Phase 3.1**: Extract 512-dimensional normalized ReID embeddings for persons using pretrained OSNet-AIN.
  * **Phase 3.2**: Use CLIP image embeddings as the vehicle ReID feature space.
  * **Phase 3.3 & 3.4**: Create a shared `identity_gallery` table in PostgreSQL and index it with HNSW cosine similarity indices to run asynchronous identity matching.
  * **Phase 4.4 & 5.1**: Build ReID trajectory and dwell time search service queries using gallery associations.
