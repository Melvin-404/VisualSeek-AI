"""Configuration for the video ingestion pipeline.

Uses pydantic-settings for environment variable loading with sensible
defaults tuned for NVIDIA H200 GPU deployment.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class RTSPConfig(BaseSettings):
    """RTSP stream capture configuration."""

    model_config = {"env_prefix": "RTSP_"}

    max_concurrent_streams: int = Field(64, description="Max simultaneous RTSP streams")
    reconnect_base_delay_s: float = Field(1.0, description="Initial reconnect delay")
    reconnect_max_delay_s: float = Field(60.0, description="Maximum reconnect delay")
    frame_timeout_s: float = Field(10.0, description="Timeout for frame reads")
    transport: str = Field("tcp", description="RTSP transport protocol (tcp/udp)")


class SegmentConfig(BaseSettings):
    """Video segmentation configuration."""

    model_config = {"env_prefix": "SEGMENT_"}

    duration_s: float = Field(30.0, description="Target segment duration in seconds")
    overlap_s: float = Field(2.0, description="Overlap between consecutive segments")
    output_codec: str = Field("mp4v", description="FourCC codec for output segments")
    output_extension: str = Field(".mp4", description="Output file extension")
    temp_dir: str = Field("vq-segments", description="Temporary directory for segments")


class QualityConfig(BaseSettings):
    """Frame quality assessment thresholds."""

    model_config = {"env_prefix": "QUALITY_"}

    blur_threshold: float = Field(100.0, description="Laplacian variance threshold for blur")
    darkness_threshold: float = Field(20.0, description="Mean luminance threshold for darkness")
    frozen_threshold: float = Field(0.98, description="SSIM threshold for frozen frame")
    check_interval_frames: int = Field(30, description="Run quality check every N frames")


class MinIOConfig(BaseSettings):
    """MinIO object storage configuration."""

    model_config = {"env_prefix": "MINIO_"}

    endpoint: str = Field("localhost:9000", description="MinIO server endpoint")
    access_key: str = Field("minioadmin", description="MinIO access key")
    secret_key: str = Field("minioadmin", description="MinIO secret key")
    bucket_name: str = Field("video-segments", description="Bucket for video segments")
    use_ssl: bool = Field(False, description="Use SSL for MinIO connection")
    multipart_threshold_mb: int = Field(50, description="Multipart upload threshold in MB")
    region: str = Field("us-east-1", description="MinIO region")


class CeleryConfig(BaseSettings):
    """Celery worker configuration."""

    model_config = {"env_prefix": "CELERY_"}

    broker_url: str = Field("redis://localhost:6379/0", description="Celery broker URL")
    result_backend: str = Field("redis://localhost:6379/1", description="Celery result backend")
    task_acks_late: bool = Field(True, description="Acknowledge tasks after completion")
    worker_prefetch_multiplier: int = Field(1, description="Fair dispatch")
    task_soft_time_limit: int = Field(3600, description="Soft time limit per task (seconds)")
    task_time_limit: int = Field(3660, description="Hard time limit per task (seconds)")


class GPUConfig(BaseSettings):
    """GPU hardware configuration."""

    model_config = {"env_prefix": "GPU_"}

    device_id: int = Field(0, description="CUDA device ID")
    enable_nvdec: bool = Field(True, description="Enable NVIDIA hardware decoding")
    cuda_buffer_pool_size: int = Field(16, description="CUDA buffer pool size for decode")


class IngestionConfig(BaseSettings):
    """Root configuration aggregating all sub-configs."""

    rtsp: RTSPConfig = Field(default_factory=RTSPConfig)
    segment: SegmentConfig = Field(default_factory=SegmentConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    minio: MinIOConfig = Field(default_factory=MinIOConfig)
    celery: CeleryConfig = Field(default_factory=CeleryConfig)
    gpu: GPUConfig = Field(default_factory=GPUConfig)
