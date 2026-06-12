"""ByteTrack tracker implementation with CUDA-accelerated IoU matching and ReID recovery."""

from enum import IntEnum
import logging
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from scipy.optimize import linear_sum_assignment
import torch

from tracking.reid_model import OSNetReID

logger = logging.getLogger(__name__)


class TrackState(IntEnum):
    """Lifecycle states for a tracked object."""

    TENTATIVE = 1
    CONFIRMED = 2
    LOST = 3
    DELETED = 4


class STrack:
    """Represents a single tracked object thread with metadata, history, and ReID features."""

    def __init__(
        self,
        bbox: np.ndarray,
        score: float,
        class_label: int,
        timestamp_ms: int,
        features: Optional[np.ndarray] = None,
    ):
        """Initialize a new track segment."""
        self.track_id = -1
        self.state = TrackState.TENTATIVE
        self.bbox = np.array(bbox, dtype=np.float32)  # [x1, y1, x2, y2]
        self.history: List[Tuple[int, np.ndarray]] = [(timestamp_ms, self.bbox.copy())]
        self.first_seen = timestamp_ms
        self.last_seen = timestamp_ms
        self.class_label = int(class_label)
        self.avg_confidence = float(score)

        self.conf_sum = float(score)
        self.hits = 1
        self.features = features  # shape (512,)
        self.metadata = {}

    def update(self, new_track: "STrack", timestamp_ms: int) -> None:
        """Update track bounding box, history, confidence, and timestamp."""
        self.bbox = new_track.bbox.copy()
        self.history.append((timestamp_ms, self.bbox.copy()))
        self.last_seen = timestamp_ms
        self.hits += 1

        self.conf_sum += new_track.avg_confidence
        self.avg_confidence = self.conf_sum / self.hits

        if new_track.features is not None:
            # Running exponential moving average for ReID embedding update
            if self.features is None:
                self.features = new_track.features.copy()
            else:
                self.features = 0.9 * self.features + 0.1 * new_track.features
                # Re-normalize to unit length
                norm = np.linalg.norm(self.features)
                if norm > 0:
                    self.features /= norm

    def mark_lost(self) -> None:
        """Mark track as lost."""
        self.state = TrackState.LOST

    def mark_deleted(self) -> None:
        """Mark track as deleted."""
        self.state = TrackState.DELETED

    def to_dict(self) -> dict:
        """Serialize track state to a dictionary."""
        return {
            "track_id": self.track_id,
            "state": int(self.state),
            "bbox": self.bbox.tolist(),
            "history": [(ts, box.tolist()) for ts, box in self.history],
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "class_label": self.class_label,
            "avg_confidence": self.avg_confidence,
            "conf_sum": self.conf_sum,
            "hits": self.hits,
            "features": self.features.tolist() if self.features is not None else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "STrack":
        """Reconstruct track from a serialized dictionary."""
        bbox = np.array(data["bbox"], dtype=np.float32)
        score = data["avg_confidence"]
        class_label = data["class_label"]
        first_seen = data["first_seen"]
        
        track = cls(bbox, score, class_label, first_seen)
        track.track_id = data["track_id"]
        track.state = TrackState(data["state"])
        track.last_seen = data["last_seen"]
        track.conf_sum = data["conf_sum"]
        track.hits = data["hits"]
        
        track.history = [(ts, np.array(box, dtype=np.float32)) for ts, box in data["history"]]
        if data["features"] is not None:
            track.features = np.array(data["features"], dtype=np.float32)
        track.metadata = data.get("metadata", {})
        return track


def compute_iou(
    box1: Union[np.ndarray, torch.Tensor], box2: Union[np.ndarray, torch.Tensor]
) -> Union[np.ndarray, torch.Tensor]:
    """Compute intersection-over-union between two sets of bounding boxes.

    Runs on GPU if inputs are PyTorch CUDA tensors, otherwise runs on CPU via NumPy.
    """
    if isinstance(box1, torch.Tensor) and isinstance(box2, torch.Tensor):
        # CUDA/Torch execution
        b1 = box1.unsqueeze(1)
        b2 = box2.unsqueeze(0)
        ix1 = torch.max(b1[..., 0], b2[..., 0])
        iy1 = torch.max(b1[..., 1], b2[..., 1])
        ix2 = torch.min(b1[..., 2], b2[..., 2])
        iy2 = torch.min(b1[..., 3], b2[..., 3])
        
        iw = torch.clamp(ix2 - ix1, min=0.0)
        ih = torch.clamp(iy2 - iy1, min=0.0)
        intersection = iw * ih
        
        area1 = (b1[..., 2] - b1[..., 0]) * (b1[..., 3] - b1[..., 1])
        area2 = (b2[..., 2] - b2[..., 0]) * (b2[..., 3] - b2[..., 1])
        union = area1 + area2 - intersection
        return intersection / torch.clamp(union, min=1e-6)
    else:
        # NumPy execution
        b1 = np.expand_dims(box1, axis=1)
        b2 = np.expand_dims(box2, axis=0)
        ix1 = np.maximum(b1[..., 0], b2[..., 0])
        iy1 = np.maximum(b1[..., 1], b2[..., 1])
        ix2 = np.minimum(b1[..., 2], b2[..., 2])
        iy2 = np.minimum(b1[..., 3], b2[..., 3])
        
        iw = np.maximum(0.0, ix2 - ix1)
        ih = np.maximum(0.0, iy2 - iy1)
        intersection = iw * ih
        
        area1 = (b1[..., 2] - b1[..., 0]) * (b1[..., 3] - b1[..., 1])
        area2 = (b2[..., 2] - b2[..., 0]) * (b2[..., 3] - b2[..., 1])
        union = area1 + area2 - intersection
        return intersection / np.maximum(union, 1e-6)


class ByteTracker:
    """Independent ByteTrack multi-object tracker per camera stream."""

    def __init__(
        self,
        track_thresh: float = 0.5,
        high_thresh: float = 0.6,
        match_thresh: float = 0.8,
        max_time_lost_ms: int = 30000,
        min_hits: int = 2,
    ):
        """Initialize the tracker settings."""
        self.track_thresh = track_thresh
        self.high_thresh = high_thresh
        self.match_thresh = match_thresh
        self.max_time_lost_ms = max_time_lost_ms
        self.min_hits = min_hits

        self.tracked_tracks: List[STrack] = []  # TENTATIVE or CONFIRMED
        self.lost_tracks: List[STrack] = []     # LOST
        self.next_track_id = 1
        self.frame_id = 0

    def update(
        self,
        detections: np.ndarray,
        frame: np.ndarray,
        timestamp_ms: int,
        reid_model: Optional[OSNetReID] = None,
    ) -> List[STrack]:
        """Update tracker with new detections in the frame.

        Args:
            detections: Bounding boxes and confidence of shape (N, 6)
                        where each is [x1, y1, x2, y2, score, class_id]
            frame: Raw BGR frame image.
            timestamp_ms: Capture timestamp in milliseconds.
            reid_model: ReID model to extract features for occlusion recovery.
        """
        self.frame_id += 1

        # Clean up stale lost tracks
        self.lost_tracks = [
            t for t in self.lost_tracks
            if (timestamp_ms - t.last_seen) <= self.max_time_lost_ms
        ]

        if len(detections) == 0:
            # Transition active tracks to lost
            for track in self.tracked_tracks:
                if track.state == TrackState.CONFIRMED:
                    track.mark_lost()
                    self.lost_tracks.append(track)
                else:
                    track.mark_deleted()
            self.tracked_tracks = []
            return []

        # 1. Split detections into high-score and low-score pools
        scores = detections[:, 4]
        high_mask = scores >= self.track_thresh
        low_mask = (scores < self.track_thresh) & (scores >= 0.1)

        det_high_raw = detections[high_mask]
        det_low_raw = detections[low_mask]

        # Extract features for high-confidence detections
        features_high = None
        if len(det_high_raw) > 0 and reid_model is not None:
            features_high = reid_model.extract_embeddings(frame, det_high_raw[:, :4].tolist())

        # Construct STrack objects for detections
        detections_high = [
            STrack(
                bbox=det[:4],
                score=det[4],
                class_label=int(det[5]),
                timestamp_ms=timestamp_ms,
                features=features_high[i] if features_high is not None else None,
            )
            for i, det in enumerate(det_high_raw)
        ]

        detections_low = [
            STrack(bbox=det[:4], score=det[4], class_label=int(det[5]), timestamp_ms=timestamp_ms)
            for det in det_low_raw
        ]

        # Combine tracked and lost tracks to match
        track_pool = self.tracked_tracks + self.lost_tracks

        # 2. Match high-confidence detections with track pool using IoU
        matched_indices, unmatched_tracks_idx, unmatched_detections_idx = self._linear_assignment(
            track_pool, detections_high, self.match_thresh
        )

        activated_tracks: List[STrack] = []
        refind_tracks: List[STrack] = []

        for t_idx, d_idx in matched_indices:
            track = track_pool[t_idx]
            det = detections_high[d_idx]
            
            # If track was lost, recover it
            if track.state == TrackState.LOST:
                track.state = TrackState.CONFIRMED
                refind_tracks.append(track)
            
            track.update(det, timestamp_ms)
            activated_tracks.append(track)

        # 3. Match low-confidence detections with remaining unmatched tracks using IoU
        remaining_tracks = [track_pool[i] for i in unmatched_tracks_idx]
        
        # Second match threshold can be slightly larger (lower IoU requirement)
        matched_indices_low, unmatched_tracks_idx_low, _ = self._linear_assignment(
            remaining_tracks, detections_low, match_thresh=0.9
        )

        for t_idx, d_idx in matched_indices_low:
            track = remaining_tracks[t_idx]
            det = detections_low[d_idx]
            if track.state == TrackState.LOST:
                track.state = TrackState.CONFIRMED
                refind_tracks.append(track)
            track.update(det, timestamp_ms)
            activated_tracks.append(track)

        # 4. Perform ReID cosine similarity matching for remaining unmatched lost tracks
        unmatched_lost_and_confirmed = [remaining_tracks[i] for i in unmatched_tracks_idx_low if remaining_tracks[i].state in {TrackState.CONFIRMED, TrackState.LOST}]
        unmatched_dets = [detections_high[i] for i in unmatched_detections_idx]

        if len(unmatched_lost_and_confirmed) > 0 and len(unmatched_dets) > 0 and reid_model is not None:
            # Cosine similarity matching
            matched_indices_reid, unmatched_tracks_reid, unmatched_dets_reid = self._reid_assignment(
                unmatched_lost_and_confirmed, unmatched_dets, dist_thresh=0.4
            )
            
            for t_idx, d_idx in matched_indices_reid:
                track = unmatched_lost_and_confirmed[t_idx]
                det = unmatched_dets[d_idx]
                if track.state == TrackState.LOST:
                    track.state = TrackState.CONFIRMED
                    refind_tracks.append(track)
                track.update(det, timestamp_ms)
                activated_tracks.append(track)
                
            unmatched_lost_and_confirmed = [unmatched_lost_and_confirmed[i] for i in unmatched_tracks_reid]
            unmatched_dets = [unmatched_dets[i] for i in unmatched_dets_reid]

        # 5. Handle remaining unmatched tracks (mark as LOST or delete TENTATIVE)
        for track in unmatched_lost_and_confirmed:
            if track.state == TrackState.CONFIRMED:
                track.mark_lost()
                self.lost_tracks.append(track)
            elif track.state == TrackState.TENTATIVE:
                track.mark_deleted()

        # Remove now confirmed/refound tracks from lost pool
        self.lost_tracks = [t for t in self.lost_tracks if t.state == TrackState.LOST]

        # 6. Initialize new tracks from unmatched high-confidence detections
        for det in unmatched_dets:
            if det.avg_confidence >= self.high_thresh:
                det.track_id = self.next_track_id
                self.next_track_id += 1
                
                # Check hits transitions immediately
                if self.min_hits <= 1:
                    det.state = TrackState.CONFIRMED
                else:
                    det.state = TrackState.TENTATIVE
                
                activated_tracks.append(det)

        # Update tracked tracks pool
        self.tracked_tracks = []
        for track in activated_tracks:
            if track.state == TrackState.TENTATIVE:
                # If tentative hits matches requirement, confirm it
                if track.hits >= self.min_hits:
                    track.state = TrackState.CONFIRMED
                self.tracked_tracks.append(track)
            elif track.state == TrackState.CONFIRMED:
                self.tracked_tracks.append(track)

        # Return only confirmed tracks that are active on the current frame
        return [t for t in self.tracked_tracks if t.state == TrackState.CONFIRMED]

    def _linear_assignment(
        self, tracks: List[STrack], detections: List[STrack], match_thresh: float
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """Match tracks and detections using Hungarian assignment based on IoU distance."""
        if len(tracks) == 0 or len(detections) == 0:
            return [], list(range(len(tracks))), list(range(len(detections)))

        # Build box matrices
        track_boxes = np.array([t.bbox for t in tracks], dtype=np.float32)
        det_boxes = np.array([d.bbox for d in detections], dtype=np.float32)

        # Check if PyTorch CUDA can be used
        if torch.cuda.is_available():
            t_box_tensor = torch.from_numpy(track_boxes).cuda()
            d_box_tensor = torch.from_numpy(det_boxes).cuda()
            iou_matrix = compute_iou(t_box_tensor, d_box_tensor).cpu().numpy()
        else:
            iou_matrix = compute_iou(track_boxes, det_boxes)

        cost_matrix = 1.0 - iou_matrix

        # Solve assignment problem
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        matched_indices = []
        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] <= match_thresh:
                matched_indices.append((int(r), int(c)))

        matched_rows = {r for r, _ in matched_indices}
        matched_cols = {c for _, c in matched_indices}

        unmatched_rows = [r for r in range(len(tracks)) if r not in matched_rows]
        unmatched_cols = [c for c in range(len(detections)) if c not in matched_cols]

        return matched_indices, unmatched_rows, unmatched_cols

    def _reid_assignment(
        self, tracks: List[STrack], detections: List[STrack], dist_thresh: float
    ) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """Match tracks and detections using Hungarian assignment based on ReID embedding distance."""
        # Filter tracks and detections that actually have features
        track_indices = [i for i, t in enumerate(tracks) if t.features is not None]
        det_indices = [i for i, d in enumerate(detections) if d.features is not None]

        if len(track_indices) == 0 or len(det_indices) == 0:
            return [], list(range(len(tracks))), list(range(len(detections)))

        # Build feature matrices
        track_feats = np.stack([tracks[i].features for i in track_indices])
        det_feats = np.stack([detections[i].features for i in det_indices])

        # Cosine distance = 1.0 - Cosine Similarity
        # Since features are L2 normalized, similarity is simple dot product
        similarity = np.dot(track_feats, det_feats.T)
        cost_matrix = 1.0 - similarity

        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        matched_indices = []
        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] <= dist_thresh:
                # Map back to original list indices
                matched_indices.append((track_indices[r], det_indices[c]))

        matched_rows = {r for r, _ in matched_indices}
        matched_cols = {c for _, c in matched_indices}

        unmatched_rows = [r for r in range(len(tracks)) if r not in matched_rows]
        unmatched_cols = [c for c in range(len(detections)) if c not in matched_cols]

        return matched_indices, unmatched_rows, unmatched_cols

    def to_dict(self) -> dict:
        """Snapshot current tracker state to JSON-serializable dictionary."""
        return {
            "frame_id": self.frame_id,
            "next_track_id": self.next_track_id,
            "tracked_tracks": [t.to_dict() for t in self.tracked_tracks],
            "lost_tracks": [t.to_dict() for t in self.lost_tracks],
        }

    def from_dict(self, data: dict) -> None:
        """Restore tracker state from snapshot dictionary."""
        self.frame_id = data["frame_id"]
        self.next_track_id = data["next_track_id"]
        self.tracked_tracks = [STrack.from_dict(t) for t in data["tracked_tracks"]]
        self.lost_tracks = [STrack.from_dict(t) for t in data["lost_tracks"]]
