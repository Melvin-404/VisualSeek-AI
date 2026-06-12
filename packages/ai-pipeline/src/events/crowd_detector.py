"""Crowd gathering detection using spatial density clustering and heatmaps."""

import logging
from typing import List

import cv2
import numpy as np

from events.base_detector import Event, EventDetector
from tracking.bytetrack import STrack

logger = logging.getLogger(__name__)


class CrowdGatheringDetector(EventDetector):
    """Detects crowd gatherings based on spatial proximity thresholds and density estimation."""

    def __init__(self, camera_id: str):
        """Initialize detector with default rules."""
        super().__init__(camera_id)
        # Default rules
        self.rules = {
            "density_threshold": 150.0,  # Max pixel distance between individuals to group them
            "count_threshold": 10,       # Minimum count to trigger crowd warning
            "severity": "HIGH",
            "zone_id": None
        }

    def _get_track_center(self, track: STrack) -> np.ndarray:
        """Get track bounding box center (x, y)."""
        x1, y1, x2, y2 = track.bbox
        return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float32)

    def _find_crowd_clusters(self, centers: np.ndarray, thresh: float) -> List[List[int]]:
        """Find clusters of tracks using Connected Components algorithm on distance threshold."""
        num_points = len(centers)
        if num_points == 0:
            return []

        # Build adjacency matrix
        # Expand dims to compute pairwise distances
        diff = centers[:, np.newaxis, :] - centers[np.newaxis, :, :]
        dist_matrix = np.linalg.norm(diff, axis=-1)
        adj = dist_matrix <= thresh

        visited = np.zeros(num_points, dtype=bool)
        clusters = []

        for i in range(num_points):
            if not visited[i]:
                # BFS/DFS to find connected component
                cluster = []
                queue = [i]
                visited[i] = True

                while queue:
                    curr = queue.pop(0)
                    cluster.append(curr)
                    # Find unvisited neighbors
                    neighbors = np.where(adj[curr] & ~visited)[0]
                    for n in neighbors:
                        visited[n] = True
                        queue.append(n)
                clusters.append(cluster)

        return clusters

    def _generate_density_heatmap(self, centers: np.ndarray, shape: tuple) -> np.ndarray:
        """Generate a low-resolution crowd density heatmap using Gaussian accumulation."""
        h, w = shape[:2]
        # Downscale grid for speed/density mapping (e.g. 10x downscale)
        scale = 10
        grid_h, grid_w = h // scale, w // scale
        
        heatmap = np.zeros((grid_h, grid_w), dtype=np.float32)
        if len(centers) == 0:
            return heatmap

        for center in centers:
            cx, cy = int(center[0] // scale), int(center[1] // scale)
            cx = max(0, min(cx, grid_w - 1))
            cy = max(0, min(cy, grid_h - 1))
            # Accumulate weight
            heatmap[cy, cx] += 1.0

        # Apply Gaussian smoothing to diffuse density across neighbors
        if heatmap.size > 0:
            heatmap = cv2.GaussianBlur(heatmap, (15, 15), 0)
            
        return heatmap

    def detect(self, tracks: List[STrack], frame: np.ndarray, timestamp_ms: int) -> List[Event]:
        """Evaluate tracks for crowd gathering events.

        Acceptance Criteria: Detect crowd > 10 people in a single frame.
        """
        # Filter tracks for person class (class ID 0)
        person_tracks = [t for t in tracks if t.class_label == 0]
        
        count_thresh = self.rules.get("count_threshold", 10)
        if len(person_tracks) < count_thresh:
            return []

        # Get track center points
        centers = np.array([self._get_track_center(t) for t in person_tracks], dtype=np.float32)
        dist_thresh = self.rules.get("density_threshold", 150.0)

        # Cluster people using proximity thresholds
        clusters = self._find_crowd_clusters(centers, dist_thresh)

        events = []
        for cluster in clusters:
            if len(cluster) >= count_thresh:
                # Crowd gathering detected in this cluster!
                zone_id = self.rules.get("zone_id")
                event_type = "crowd_gathering"

                # Deduplicate before building full payload
                if self.should_suppress(event_type, zone_id, timestamp_ms):
                    continue

                cluster_tracks = [person_tracks[i] for i in cluster]
                cluster_centers = centers[cluster]

                # Compute cluster centroid and bounding box
                centroid = cluster_centers.mean(axis=0)
                min_x = float(cluster_centers[:, 0].min())
                min_y = float(cluster_centers[:, 1].min())
                max_x = float(cluster_centers[:, 0].max())
                max_y = float(cluster_centers[:, 1].max())

                # Generate density heatmap for cluster localization
                heatmap = self._generate_density_heatmap(cluster_centers, frame.shape)
                max_density = float(heatmap.max())

                events.append(
                    Event(
                        camera_id=self.camera_id,
                        event_type=event_type,
                        severity=self.rules.get("severity", "HIGH"),
                        timestamp_ms=timestamp_ms,
                        zone_id=zone_id,
                        metadata={
                            "people_count": len(cluster),
                            "centroid": [float(centroid[0]), float(centroid[1])],
                            "bounding_box": [min_x, min_y, max_x, max_y],
                            "max_density": max_density,
                            "track_ids": [t.track_id for t in cluster_tracks],
                        },
                    )
                )

        return events
