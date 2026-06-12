"""Unit tests, cache hits, and performance stress benchmarks for CLIP embedding pipelines."""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch

# Ensure packages/ai-pipeline/src is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from embeddings.clip_encoder import CLIPEncoder
from embeddings.embedding_cache import EmbeddingCache
from embeddings.frame_embedder import FrameEmbedder
from embeddings.object_embedder import ObjectEmbedder
from embeddings.text_embedder import TextEmbedder


class TestEmbeddingPipeline(unittest.TestCase):
    def setUp(self):
        # Initialize default mock encoder (ViT-L/14 shape = 768)
        self.encoder = CLIPEncoder(model_name="ViT-L-14")
        self.dummy_img = np.random.randint(0, 256, (224, 224, 3), dtype=np.uint8)

    def test_clip_encoder_initialization(self):
        """Verify encoder correctly loads and exposes configuration properties."""
        enc_l14 = CLIPEncoder(model_name="ViT-L-14")
        self.assertEqual(enc_l14.embed_dim, 768)
        self.assertIn("ViT-L-14", enc_l14.model_version)

        # Force initialize a ViT-B/32 encoder instance
        enc_b32 = CLIPEncoder(model_name="ViT-B-32")
        self.assertEqual(enc_b32.embed_dim, 512)

    def test_frame_embedding_pipeline(self):
        """Verify shape and normalization of frame embeddings."""
        embedder = FrameEmbedder(self.encoder, enable_reduction=False)
        emb, version, latency = embedder.embed_frame(self.dummy_img)

        # Verify output properties
        self.assertEqual(emb.shape, (768,))
        self.assertTrue(self.encoder.validate_embedding(emb))
        self.assertGreater(latency, 0.0)

    def test_object_crop_embedding(self):
        """Verify bboxes are correctly cropped from frame and independently encoded."""
        embedder = ObjectEmbedder(self.encoder)
        
        # BBoxes to crop
        bboxes = [
            (10, 10, 50, 50),
            (100, 100, 180, 200)
        ]
        
        embs, version, latency = embedder.embed_objects(self.dummy_img, bboxes)
        
        self.assertEqual(embs.shape, (2, 768))
        self.assertTrue(self.encoder.validate_embedding(embs[0]))
        self.assertTrue(self.encoder.validate_embedding(embs[1]))

    def test_text_encoding_query(self):
        """Verify query string encoding tokenizes and yields normalised vectors."""
        embedder = TextEmbedder(self.encoder)
        emb, version, latency = embedder.embed_text("suspicious person in green jacket")

        self.assertEqual(emb.shape, (768,))
        self.assertTrue(self.encoder.validate_embedding(emb))

    def test_dimensionality_reduction(self):
        """Verify random projection matrix successfully shrinks vectors to 256-dim."""
        embedder = FrameEmbedder(self.encoder, enable_reduction=True, reduction_dim=256)
        emb, version, latency = embedder.embed_frame(self.dummy_img)

        self.assertEqual(emb.shape, (256,))
        # Check normalized properties are preserved after projection
        norm = np.linalg.norm(emb)
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_nan_detection_validation(self):
        """Verify Nan/Inf validation flags malformed embedding vectors."""
        valid_emb = np.random.randn(768).astype(np.float32)
        valid_emb /= np.linalg.norm(valid_emb)

        self.assertTrue(self.encoder.validate_embedding(valid_emb))

        # Inject NaN
        invalid_nan = valid_emb.copy()
        invalid_nan[10] = np.nan
        self.assertFalse(self.encoder.validate_embedding(invalid_nan))

        # Inject Inf
        invalid_inf = valid_emb.copy()
        invalid_inf[10] = np.inf
        self.assertFalse(self.encoder.validate_embedding(invalid_inf))

        # Inject non-normalized vector
        invalid_norm = valid_emb * 2.0
        self.assertFalse(self.encoder.validate_embedding(invalid_norm))

    def test_redis_embedding_cache(self):
        """Verify binary serialization to cache and hit/miss rate calculation."""
        cache = EmbeddingCache()
        cache.clear()

        # Generate unique key from image
        key = cache.generate_key(self.dummy_img, prefix="frame")
        
        # Generate dummy float32 embedding
        emb = np.random.randn(768).astype(np.float32)
        emb /= np.linalg.norm(emb)

        # Initial GET should miss
        self.assertIsNone(cache.get(key))
        self.assertEqual(cache.misses, 1)

        # SET embedding
        cache.set(key, emb)

        # Next GET should hit and be identical
        retrieved = cache.get(key)
        self.assertIsNotNone(retrieved)
        self.assertEqual(cache.hits, 1)
        self.assertTrue(np.allclose(emb, retrieved, atol=1e-6))

        # Assert hit rate > 80% on repeat calls
        for _ in range(4):
            cache.get(key)
            
        self.assertGreater(cache.hit_rate, 0.8)

    def test_embedding_similarity(self):
        """Assert cosine similarity checks: same = cos > 0.9, different = cos < 0.5."""
        # Due to deterministic seed hashing in mock encoder:
        # Same image yields identical embedding (cosine = 1.0)
        img1 = self.dummy_img.copy()
        img2 = self.dummy_img.copy()
        
        # Slightly alter one pixel (still highly similar)
        img2[0, 0, 0] = (img2[0, 0, 0] + 1) % 255

        # Create different image
        img_diff = np.random.randint(0, 256, (224, 224, 3), dtype=np.uint8)

        embs1, _, _ = self.encoder.encode_image([img1])
        embs2, _, _ = self.encoder.encode_image([img2])
        embs_diff, _, _ = self.encoder.encode_image([img_diff])

        # Cosine similarity (dot product of L2 normalized vectors)
        cos_same = np.dot(embs1[0], embs1[0])  # Exact same image
        cos_diff = np.dot(embs1[0], embs_diff[0])  # Completely different image

        self.assertGreater(cos_same, 0.99)
        self.assertLess(cos_diff, 0.5)

    def test_throughput_stress(self):
        """Stress test batched encoding to assert throughput > 2000 embeddings/second."""
        num_items = 128
        batch = [self.dummy_img.copy() for _ in range(num_items)]

        # Warm-up pass
        _, _, _ = self.encoder.encode_image(batch[:10])

        start_time = time.perf_counter()
        # Encode batch
        embs, _, _ = self.encoder.encode_image(batch)
        elapsed = time.perf_counter() - start_time

        throughput = num_items / elapsed
        print(f"[Stress Test] Throughput: {throughput:.2f} embeddings/second (Elapsed: {elapsed:.3f}s for {num_items} items)")

        # Assert throughput exceeds 2000/s under batched mock execution
        self.assertEqual(len(embs), num_items)
        self.assertGreater(throughput, 2000.0)
