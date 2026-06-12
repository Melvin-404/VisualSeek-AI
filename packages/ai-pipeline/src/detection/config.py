"""Configuration settings for YOLOv10 object detection and TensorRT inference."""

from typing import Dict
from pydantic_settings import BaseSettings
from pydantic import Field


class DetectionConfig(BaseSettings):
    """Configuration for YOLOv10 TensorRT deployment."""

    model_config = {"env_prefix": "DETECTION_"}

    model_name: str = Field("yolov10x", description="YOLOv10 model name")
    model_path: str = Field("models/yolov10x.onnx", description="Path to source ONNX model")
    engine_path: str = Field("models/yolov10x.engine", description="Path to compile/load TensorRT engine")
    calibration_cache_path: str = Field("models/yolov10x_calib.cache", description="INT8 calibration cache path")
    
    max_batch_size: int = Field(64, description="Max dynamic batch size for TensorRT engine")
    enable_int8: bool = Field(True, description="Enable INT8 quantization")
    enable_fp16: bool = Field(True, description="Enable FP16 precision fallback")
    
    iou_threshold: float = Field(0.45, description="NMS Intersection-over-Union threshold")
    
    confidence_thresholds: Dict[str, float] = Field(
        default_factory=lambda: {"person": 0.4, "vehicle": 0.5, "object": 0.3},
        description="Class-specific confidence thresholds"
    )
    
    triton_server_url: str = Field("localhost:8001", description="NVIDIA Triton gRPC server URL")
    enable_triton: bool = Field(False, description="Enable Triton Server mode (falls back to local TRT if false)")
