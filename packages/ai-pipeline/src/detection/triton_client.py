"""Triton Inference Server client integration with local fallback execution."""

import logging
from typing import List, Optional, Tuple

import numpy as np
import torch

from detection.config import DetectionConfig
from detection.postprocessor import DetectionResult, Postprocessor
from detection.yolo_engine import YOLOTensorRTEngine

try:
    import tritonclient.grpc as grpcclient
    HAS_TRITON_GRPC = True
except ImportError:
    grpcclient = None
    HAS_TRITON_GRPC = False

try:
    import tritonclient.http as httpclient
    HAS_TRITON_HTTP = True
except ImportError:
    httpclient = None
    HAS_TRITON_HTTP = False

logger = logging.getLogger(__name__)


class TritonInferenceClient:
    """gRPC/HTTP Triton Inference Server client with dynamic local engine fallback."""

    def __init__(self, config: DetectionConfig, local_engine: Optional[YOLOTensorRTEngine] = None):
        """Initialize Triton client and local fallback engine."""
        self.config = config
        self.postprocessor = Postprocessor(config)

        # Initialize local fallback engine
        self.local_engine = local_engine
        if self.local_engine is None:
            self.local_engine = YOLOTensorRTEngine(config)
            self.local_engine.load_engine()

        self.grpc_client = None
        self.http_client = None
        self.connected = False

        if self.config.enable_triton:
            self._establish_connections()

    def _establish_connections(self) -> None:
        """Attempt to connect to the Triton server."""
        # Try gRPC first
        if HAS_TRITON_GRPC:
            try:
                logger.info("Attempting Triton gRPC connection to %s", self.config.triton_server_url)
                # URL is usually localhost:8001 (gRPC) or localhost:8000 (HTTP)
                self.grpc_client = grpcclient.InferenceServerClient(
                    url=self.config.triton_server_url, verbose=False
                )
                # Check if server is alive
                if self.grpc_client.is_server_live():
                    logger.info("Triton gRPC server is live.")
                    self.connected = True
                    return
            except Exception as e:
                logger.debug("Triton gRPC connection failed: %s", e)

        # Fallback to HTTP
        if HAS_TRITON_HTTP:
            try:
                # Deduce HTTP port from gRPC port if possible (usually 8000 instead of 8001)
                url = self.config.triton_server_url
                if "8001" in url:
                    url = url.replace("8001", "8000")
                logger.info("Attempting Triton HTTP connection to %s", url)
                self.http_client = httpclient.InferenceServerClient(url=url, verbose=False)
                if self.http_client.is_server_live():
                    logger.info("Triton HTTP server is live.")
                    self.connected = True
                    return
            except Exception as e:
                logger.debug("Triton HTTP connection failed: %s", e)

        logger.warning("Could not establish connection to Triton server. Falling back to local engine.")
        self.connected = False

    def infer(
        self, batch_tensor: torch.Tensor, original_dims: List[Tuple[int, int]]
    ) -> List[List[DetectionResult]]:
        """Run batch inference.

        If Triton client is connected and active, uses Triton. Otherwise, falls back to the local engine.

        Args:
            batch_tensor: Preprocessed tensor of shape (B, C, H, W).
            original_dims: List of original dimensions (width, height) of frames in batch.
        """
        raw_outputs = None

        # 1. Triton Execution path
        if self.config.enable_triton and self.connected:
            try:
                # Convert torch tensor to numpy
                np_input = batch_tensor.cpu().numpy().astype(np.float32)
                input_name = "images"
                output_name = "output0"

                if self.grpc_client is not None:
                    # gRPC inference request
                    inputs = [
                        grpcclient.InferInput(input_name, list(np_input.shape), "FP32")
                    ]
                    inputs[0].set_data_from_numpy(np_input)
                    outputs = [grpcclient.InferRequestedOutput(output_name)]

                    response = self.grpc_client.infer(
                        model_name=self.config.model_name,
                        inputs=inputs,
                        outputs=outputs,
                        timeout=5.0,
                    )
                    raw_outputs = response.as_numpy(output_name)

                elif self.http_client is not None:
                    # HTTP inference request
                    inputs = [
                        httpclient.InferInput(input_name, list(np_input.shape), "FP32")
                    ]
                    inputs[0].set_data_from_numpy(np_input)
                    outputs = [httpclient.InferRequestedOutput(output_name)]

                    response = self.http_client.infer(
                        model_name=self.config.model_name,
                        inputs=inputs,
                        outputs=outputs,
                        timeout=5.0,
                    )
                    raw_outputs = response.as_numpy(output_name)

            except Exception as e:
                logger.warning("Triton inference failed: %s. Falling back to local execution.", e)
                # Mark connection as lost to avoid constant timeouts
                self.connected = False

        # 2. Local Fallback Execution path
        if raw_outputs is None:
            raw_outputs = self.local_engine.execute_inference(batch_tensor)

        # 3. Postprocess and return
        return self.postprocessor.postprocess(raw_outputs, original_dims)
