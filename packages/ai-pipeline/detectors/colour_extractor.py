import cv2
import numpy as np
from sklearn.cluster import KMeans

# Pre-generate 64x64 Gaussian mask with sigma=20
_AX = np.arange(64) - 31.5
_XX, _YY = np.meshgrid(_AX, _AX)
_MASK_64 = np.exp(-(_XX**2 + _YY**2) / (2.0 * 20.0**2))
_MASK_64 = _MASK_64 / np.max(_MASK_64)

# Subsample mask to 16x16 (every 4th pixel)
_MASK_16 = _MASK_64[::4, ::4]
_WEIGHTS_16 = _MASK_16.reshape(-1)

def map_hsv_to_color_name(h: float, s: float, v: float) -> str:
    """Maps OpenCV scale HSV values to one of 12 human-readable color names.
    
    OpenCV HSV range: H [0-180], S [0-255], V [0-255].
    """
    # 1. Black: V < 50
    if v < 50:
        return "black"
    
    # 2. White: S < 30 and V > 200
    if s < 30 and v > 200:
        return "white"
    
    # 3. Grey: S < 40 and 50 <= V <= 200
    if s < 40 and 50 <= v <= 200:
        return "grey"
        
    # 4. Brown: H: 10-20, S > 80, V < 150
    if 10 <= h <= 20 and s > 80 and v < 150:
        return "brown"
        
    # Hue ranges (0-180 in OpenCV)
    if 0 <= h <= 10 or 170 <= h <= 180:
        return "red"
    elif 10 <= h < 25:
        return "orange"
    elif 25 <= h < 35:
        return "yellow"
    elif 35 <= h < 85:
        return "green"
    elif 85 <= h < 100:
        return "cyan"
    elif 100 <= h < 130:
        return "blue"
    elif 130 <= h < 145:
        return "purple"
    elif 145 <= h < 170:
        return "pink"
        
    return "grey"

class DominantColourExtractor:
    """Zero GPU cost dominant color extractor running on CPU under 3ms."""

    def __init__(self):
        # Pre-initialize KMeans to reuse settings
        self.kmeans = KMeans(
            n_clusters=3,
            n_init=1,
            max_iter=3,
            tol=1.0,
            random_state=42
        )

    def extract(self, crop: np.ndarray) -> dict:
        """Extracts dominant color from BGR crop.
        
        Args:
            crop: BGR image crop (numpy array).
            
        Returns:
            Dict containing: dominant_colour, colour_confidence, hsv_h, hsv_s, hsv_v
        """
        if crop is None or crop.size == 0:
            return {
                "dominant_colour": "unknown",
                "colour_confidence": 0.0,
                "hsv_h": 0,
                "hsv_s": 0,
                "hsv_v": 0
            }

        # 1. Resize crop to 64x64
        crop_64 = cv2.resize(crop, (64, 64))

        # 2. Convert from BGR to HSV
        hsv_64 = cv2.cvtColor(crop_64, cv2.COLOR_BGR2HSV)

        # 3. Subsample to 16x16 for CPU performance constraint (<3ms)
        hsv_16 = hsv_64[::4, ::4]
        pixels = hsv_16.reshape(-1, 3).astype(np.float32)

        # 4. Fit KMeans K=3 weighted by Gaussian mask
        self.kmeans.fit(pixels, sample_weight=_WEIGHTS_16)

        # 5. Find cluster with the highest total weight
        labels = self.kmeans.labels_
        cluster_weights = np.zeros(3)
        for i in range(3):
            cluster_weights[i] = np.sum(_WEIGHTS_16[labels == i])

        best_cluster_idx = np.argmax(cluster_weights)
        total_weight = np.sum(cluster_weights)
        confidence = float(cluster_weights[best_cluster_idx] / max(total_weight, 1e-6))

        # Get dominant HSV
        dominant_hsv = self.kmeans.cluster_centers_[best_cluster_idx]
        h, s, v = dominant_hsv[0], dominant_hsv[1], dominant_hsv[2]

        # 6. Map dominant HSV to color name
        color_name = map_hsv_to_color_name(h, s, v)

        # Output HSV_H scaled to standard 360-degree representation
        return {
            "dominant_colour": color_name,
            "colour_confidence": round(confidence, 4),
            "hsv_h": int(round(h * 2.0)),
            "hsv_s": int(round(s)),
            "hsv_v": int(round(v))
        }
