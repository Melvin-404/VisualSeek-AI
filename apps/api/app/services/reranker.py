import structlog
from typing import List, Dict, Any, Tuple
import difflib

logger = structlog.get_logger("reranker")


class Reranker:
    """Cross-Encoder re-ranker for ordering search results, with lightweight string similarity fallback."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self.model = None
        self.is_fallback = True

        # Lazy load Cross-Encoder only if GPU is available to avoid blocking CPU tests with long downloads
        try:
            import torch
            if torch.cuda.is_available():
                from sentence_transformers import CrossEncoder
                self.model = CrossEncoder(self.model_name, max_length=512)
                self.is_fallback = False
                logger.info("SentenceTransformers CrossEncoder loaded on GPU.", model=self.model_name)
            else:
                logger.info("No GPU detected. Using lightweight string similarity fallback re-ranker.")
        except Exception as e:
            logger.warning("Could not load CrossEncoder model. Using fallback string similarity re-ranker.", error=str(e))

    def rerank(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Re-scores and re-ranks search results based on Cross-Encoder match or text similarity."""
        if not results:
            return []

        # Prepare text descriptions of results
        pairs = []
        for res in results:
            doc_text = self._build_document_text(res)
            pairs.append((query, doc_text))

        scores = []
        if not self.is_fallback and self.model is not None:
            try:
                # Get cross-encoder scores
                raw_scores = self.model.predict(pairs)
                # Map scores (which are logit outputs) to a 0.0 - 1.0 range using sigmoid
                import numpy as np
                scores = (1.0 / (1.0 + np.exp(-raw_scores))).tolist()
            except Exception as e:
                logger.error("Error running Cross-Encoder inference. Falling back to text similarity.", error=str(e))
                scores = [self._fallback_score(query, pair[1]) for pair in pairs]
        else:
            scores = [self._fallback_score(query, pair[1]) for pair in pairs]

        # Combine results with new rerank score
        for res, score in zip(results, scores):
            # Mix the original Milvus cosine similarity with the cross-encoder score
            milvus_score = res.get("score", 0.0)
            # Clip milvus score to 0-1
            milvus_score = max(0.0, min(1.0, milvus_score))
            
            # Weighted average: 30% Milvus ANN score, 70% Re-ranker score
            combined_score = 0.3 * milvus_score + 0.7 * score
            res["rerank_score"] = float(combined_score)

        # Sort descending by rerank score
        ranked_results = sorted(results, key=lambda x: x["rerank_score"], reverse=True)
        return ranked_results

    def _build_document_text(self, result: Dict[str, Any]) -> str:
        """Formulates a natural text description for a Milvus search record."""
        # Event result
        if "event_type" in result:
            event_type = result.get("event_type", "")
            severity = result.get("severity", "")
            metadata = result.get("metadata", {}) or {}
            desc = metadata.get("description", "")
            return f"An event of type {event_type} with severity {severity}. {desc}".strip()
            
        # Object crop result
        elif "class_label" in result:
            class_label = result.get("class_label", "")
            camera_id = result.get("camera_id", "")
            return f"A cropped object of class {class_label} spotted on camera {camera_id}."
            
        # Frame result
        else:
            raw_labels = result.get("raw_labels", {}) or {}
            desc = raw_labels.get("description", "")
            if desc:
                return f"A frame on camera {result.get('camera_id', '')} showing: {desc}"
            
            object_classes = result.get("object_classes", []) or []
            camera_id = result.get("camera_id", "")
            detections = raw_labels.get("detections", []) or []
            
            det_summary = ", ".join([f"{d.get('label', '')}" for d in detections if d.get("label")])
            if det_summary:
                return f"A frame on camera {camera_id} containing: {det_summary}."
            elif object_classes:
                return f"A frame on camera {camera_id} showing: {', '.join(object_classes)}."
            return f"A video frame recorded on camera {camera_id}."

    def _fallback_score(self, query: str, doc_text: str) -> float:
        """Computes a token-based text similarity ratio as fallback."""
        q_tokens = set(query.lower().split())
        d_tokens = set(doc_text.lower().split())
        if not q_tokens:
            return 0.0
            
        intersection = q_tokens.intersection(d_tokens)
        seq_ratio = difflib.SequenceMatcher(None, query.lower(), doc_text.lower()).ratio()
        token_ratio = len(intersection) / len(q_tokens)
        
        return 0.4 * seq_ratio + 0.6 * token_ratio
