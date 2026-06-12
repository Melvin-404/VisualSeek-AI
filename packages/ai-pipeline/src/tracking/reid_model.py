"""Re-Identification (ReID) feature extraction using OSNet with fallbacks."""

import logging
from typing import List, Tuple

import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms

logger = logging.getLogger(__name__)

# Try to import torchreid
try:
    import torchreid
    HAS_TORCHREID = True
except ImportError:
    torchreid = None
    HAS_TORCHREID = False


class OSNetReID:
    """Extracts 512-dimensional normalized embeddings from image patches for track re-identification."""

    def __init__(self, use_gpu: bool = True):
        """Initialize the ReID model context."""
        self.device = torch.device("cuda" if use_gpu and torch.cuda.is_available() else "cpu")
        self.model = None

        # Standard ReID image preprocessing
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((256, 128)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

        self._init_model()

    def _init_model(self) -> None:
        """Initialize ReID model (OSNet or torchvision fallback)."""
        if HAS_TORCHREID:
            try:
                logger.info("Initializing OSNet x1_0 using torchreid...")
                self.model = torchreid.models.build_model(
                    name="osnet_x1_0",
                    num_classes=1000,
                    pretrained=True
                )
                self.model.to(self.device)
                self.model.eval()
                return
            except Exception as e:
                logger.warning("Failed to initialize torchreid OSNet: %s. Falling back to torchvision ResNet.", e)

        # Fallback to torchvision ResNet18 (outputs 512-dimensional features directly after pooling)
        try:
            logger.info("Initializing torchvision ResNet-18 fallback ReID extractor...")
            from torchvision.models import resnet18, ResNet18_Weights
            
            # Use weights if offline/local cache is available, otherwise initialize default
            try:
                resnet = resnet18(weights=ResNet18_Weights.DEFAULT)
            except Exception:
                logger.warning("Could not download pretrained ResNet-18 weights. Initializing random ResNet-18.")
                resnet = resnet18()

            # Remove final fc classification layer to get 512-dim features
            self.model = nn.Sequential(*list(resnet.children())[:-1])
            self.model.to(self.device)
            self.model.eval()
        except Exception as e:
            logger.error("Failed to initialize torchvision ResNet-18 ReID fallback: %s. Using random embedding generator.", e)

    def extract_embeddings(
        self, frame: np.ndarray, bboxes: List[Tuple[float, float, float, float]]
    ) -> np.ndarray:
        """Crop bounding boxes from frame and extract normalized 512-dimensional embeddings.

        Args:
            frame: Input image numpy array (BGR or RGB).
            bboxes: List of bounding boxes as [x1, y1, x2, y2].

        Returns:
            Numpy array of shape (num_bboxes, 512) containing normalized embeddings.
        """
        if len(bboxes) == 0:
            return np.empty((0, 512), dtype=np.float32)

        h, w = frame.shape[:2]
        patches = []

        for box in bboxes:
            x1, y1, x2, y2 = map(int, box)
            # Clip coordinates to frame boundaries
            x1 = max(0, min(x1, w - 1))
            y1 = max(0, min(y1, h - 1))
            x2 = max(0, min(x2, w - 1))
            y2 = max(0, min(y2, h - 1))

            # Crop patch
            if x2 > x1 and y2 > y1:
                patch = frame[y1:y2, x1:x2]
                # Convert BGR to RGB if needed (assuming cv2 BGR format)
                patch = cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)
            else:
                # Dummy patch for invalid coordinates
                patch = np.zeros((256, 128, 3), dtype=np.uint8)

            # Preprocess
            patch_tensor = self.transform(patch)
            patches.append(patch_tensor)

        # Batch features
        batch_tensor = torch.stack(patches).to(self.device)

        with torch.no_grad():
            if self.model is not None:
                features_tensor = self.model(batch_tensor)
                # ResNet outputs shape [B, 512, 1, 1] after pooling, flatten it
                features_tensor = features_tensor.view(features_tensor.size(0), -1)
                
                # Normalize features to unit length (L2 norm)
                norm = features_tensor.norm(p=2, dim=1, keepdim=True)
                normalized_features = features_tensor.div(norm)
                features = normalized_features.cpu().numpy()
            else:
                # Dummy embedding generation if model is missing
                logger.debug("No model initialized. Generating random mock features.")
                raw_feats = np.random.randn(len(bboxes), 512).astype(np.float32)
                norms = np.linalg.norm(raw_feats, axis=1, keepdims=True)
                features = raw_feats / np.maximum(norms, 1e-6)

        return features
