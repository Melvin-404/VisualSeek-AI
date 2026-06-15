import cv2
import torch
import timm
from torchvision import transforms
from typing import List, Dict
import numpy as np

# Map ImageNet class indexes to vehicle styles
VEHICLE_SYNSET_MAP: Dict[int, str] = {
    656: "sedan", 817: "sedan", 627: "sedan",
    751: "SUV", 867: "SUV",
    555: "truck", 569: "truck",
    734: "van",
    665: "motorcycle", 670: "motorcycle",
    779: "bus", 874: "bus"
}

class VehicleAttributeClassifier:
    """Classifies vehicle crops into styles using MobileNetV3-Large in FP16 on GPU."""

    def __init__(self, use_gpu: bool = True):
        self.device = torch.device("cuda" if use_gpu and torch.cuda.is_available() else "cpu")
        self.use_fp16 = self.device.type == "cuda"

        if self.device.type == "cpu":
            import logging
            logging.getLogger(__name__).warning("CUDA not available. Loading MobileNetV3 vehicle classifier on CPU.")

        try:
            # Load pretrained model
            self.model = timm.create_model("mobilenetv3_large_100.ra_in1k", pretrained=True)
            self.model.to(self.device)
            self.model.eval()
            if self.use_fp16:
                self.model = self.model.half()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to load MobileNetV3 model: {e}")
            self.model = None

        # ImageNet standard preprocessing transforms
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

    def classify_batch(self, crops: List[np.ndarray]) -> List[dict]:
        """Classifies a batch of crops. Batch size should be capped externally (e.g. 8)."""
        if self.model is None or not crops:
            return [{"vehicle_type": "unknown", "vehicle_type_confidence": 0.0} for _ in crops]

        tensors = []
        for crop in crops:
            if crop is None or crop.size == 0:
                # Dummy empty tensor if crop is invalid
                crop = np.zeros((224, 224, 3), dtype=np.uint8)
            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            tensors.append(self.transform(crop_rgb))

        batch_tensor = torch.stack(tensors).to(self.device)
        if self.use_fp16:
            batch_tensor = batch_tensor.half()

        with torch.no_grad():
            outputs = self.model(batch_tensor)
            probabilities = torch.softmax(outputs, dim=-1)
            top5_conf, top5_indices = torch.topk(probabilities, 5, dim=-1)

        results = []
        for i in range(len(crops)):
            img_indices = top5_indices[i].cpu().tolist()
            img_confs = top5_conf[i].cpu().tolist()

            vehicle_type = "unknown"
            vehicle_type_confidence = 0.0

            # Select the highest-confidence match in the lookup table
            for idx, conf in zip(img_indices, img_confs):
                if idx in VEHICLE_SYNSET_MAP:
                    vehicle_type = VEHICLE_SYNSET_MAP[idx]
                    vehicle_type_confidence = round(float(conf), 4)
                    break

            results.append({
                "vehicle_type": vehicle_type,
                "vehicle_type_confidence": vehicle_type_confidence
            })

        return results
