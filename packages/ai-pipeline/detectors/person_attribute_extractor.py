import cv2
import numpy as np
import torch
from typing import List, Dict, Tuple
from embeddings.clip_encoder import CLIPEncoder

def softmax(x: np.ndarray) -> np.ndarray:
    """Computes softmax probabilities over a 1D numpy array."""
    e_x = np.exp(x - np.max(x))
    return e_x / np.max([np.sum(e_x), 1e-6])

class PersonAttributeExtractor:
    """Extracts clothing color, carried items, and gender from person crops using zero-shot CLIP classification."""

    def __init__(self):
        # Obtain existing singleton CLIPEncoder
        self.encoder = CLIPEncoder(model_name="ViT-B-32")

        # Fixed prompt lists and corresponding labels
        self.upper_prompts = [
            "a person wearing a red top", "a person wearing a blue top", "a person wearing a green top",
            "a person wearing a black top", "a person wearing a white top", "a person wearing a grey top",
            "a person wearing a yellow top", "a person wearing an orange top", "a person wearing a brown top",
            "a person wearing a purple top"
        ]
        self.upper_labels = ["red", "blue", "green", "black", "white", "grey", "yellow", "orange", "brown", "purple"]

        self.lower_prompts = [
            "a person wearing black trousers", "a person wearing blue jeans", "a person wearing grey trousers",
            "a person wearing white trousers", "a person wearing brown trousers", "a person wearing beige trousers",
            "a person wearing a dark skirt", "a person wearing a light skirt"
        ]
        self.lower_labels = ["black", "blue", "grey", "white", "brown", "beige", "dark", "light"]

        self.carried_prompts = [
            "a person carrying an umbrella", "a person carrying a backpack", "a person carrying a bag",
            "a person carrying a suitcase", "a person carrying a shopping bag", "a person holding a phone",
            "a person wearing a hard hat", "a person wearing a hi-vis vest", "a person wearing a helmet"
        ]
        self.carried_labels = ["umbrella", "backpack", "bag", "suitcase", "shopping bag", "phone", "hard hat", "hi-vis vest", "helmet"]

        self.gender_prompts = ["a man", "a woman", "a child"]
        self.gender_labels = ["man", "woman", "child"]

        # Cache text embeddings at startup (they never change)
        self.upper_vectors, _, _ = self.encoder.encode_text(self.upper_prompts)
        self.lower_vectors, _, _ = self.encoder.encode_text(self.lower_prompts)
        self.carried_vectors, _, _ = self.encoder.encode_text(self.carried_prompts)
        self.gender_vectors, _, _ = self.encoder.encode_text(self.gender_prompts)

    def extract(self, crop: np.ndarray) -> dict:
        """Extracts attributes from BGR person crop.
        
        Args:
            crop: BGR image crop (numpy array).
            
        Returns:
            Dict containing upper_colour, upper_colour_conf, lower_colour, lower_colour_conf,
            carried_items, carried_items_conf, gender_estimate, gender_estimate_conf, gender_is_estimate
        """
        if crop is None or crop.size == 0:
            return {
                "upper_colour": "unknown", "upper_colour_conf": 0.0,
                "lower_colour": "unknown", "lower_colour_conf": 0.0,
                "carried_items": [], "carried_items_conf": [],
                "gender_estimate": "unknown", "gender_estimate_conf": 0.0,
                "gender_is_estimate": True
            }

        # 1. Convert crop BGR -> RGB for CLIP
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

        # 2. Generate CLIP Image Embedding (L2-normalized)
        img_emb_batch, _, _ = self.encoder.encode_image([crop_rgb])
        if img_emb_batch.shape[0] == 0:
            return {
                "upper_colour": "unknown", "upper_colour_conf": 0.0,
                "lower_colour": "unknown", "lower_colour_conf": 0.0,
                "carried_items": [], "carried_items_conf": [],
                "gender_estimate": "unknown", "gender_estimate_conf": 0.0,
                "gender_is_estimate": True
            }
        img_vector = img_emb_batch[0]

        # 3. Determine logit scale
        logit_scale = 100.0
        if self.encoder.model is not None and hasattr(self.encoder.model, "logit_scale"):
            with torch.no_grad():
                logit_scale = float(self.encoder.model.logit_scale.exp().cpu().item())

        # 4. Cosine similarities (dot products)
        upper_sims = np.dot(self.upper_vectors, img_vector)
        lower_sims = np.dot(self.lower_vectors, img_vector)
        carried_sims = np.dot(self.carried_vectors, img_vector)
        gender_sims = np.dot(self.gender_vectors, img_vector)

        # 5. Mutually exclusive softmax classifications
        upper_probs = softmax(upper_sims * logit_scale)
        upper_idx = np.argmax(upper_probs)
        upper_color = self.upper_labels[upper_idx]
        upper_conf = float(upper_probs[upper_idx])

        lower_probs = softmax(lower_sims * logit_scale)
        lower_idx = np.argmax(lower_probs)
        lower_color = self.lower_labels[lower_idx]
        lower_conf = float(lower_probs[lower_idx])

        gender_probs = softmax(gender_sims * logit_scale)
        gender_idx = np.argmax(gender_probs)
        gender_est = self.gender_labels[gender_idx]
        gender_conf = float(gender_probs[gender_idx])

        # 6. Multi-label classification for carried items (threshold = 0.25)
        carried_items = []
        carried_items_conf = []
        for idx, sim in enumerate(carried_sims):
            if sim > 0.25:
                carried_items.append(self.carried_labels[idx])
                carried_items_conf.append(round(float(sim), 4))

        return {
            "upper_colour": upper_color,
            "upper_colour_conf": round(upper_conf, 4),
            "lower_colour": lower_color,
            "lower_colour_conf": round(lower_conf, 4),
            "carried_items": carried_items,
            "carried_items_conf": carried_items_conf,
            "gender_estimate": gender_est,
            "gender_estimate_conf": round(gender_conf, 4),
            "gender_is_estimate": True
        }
