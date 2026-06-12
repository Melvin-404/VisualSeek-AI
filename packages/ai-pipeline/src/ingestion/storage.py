"""MinIO object storage for video segments.

Handles uploading completed video segments to MinIO with multipart
support, server-side encryption (AES-256), metadata tagging,
and presigned URL generation for frontend playback.
"""

import logging
import os
import time
from typing import Optional

from minio import Minio
from minio.error import S3Error
from minio.sse import SseS3

from ingestion.config import IngestionConfig
from ingestion.segmenter import SegmentResult

logger = logging.getLogger(__name__)


class MinIOVideoStorage:
    """Manages video segment storage in MinIO.

    Provides upload with retry, multipart support for large files,
    server-side encryption, and presigned URL generation.

    Args:
        config: Ingestion configuration with MinIO settings.
    """

    def __init__(self, config: Optional[IngestionConfig] = None) -> None:
        self.config = config or IngestionConfig()
        self._client = Minio(
            self.config.minio.endpoint,
            access_key=self.config.minio.access_key,
            secret_key=self.config.minio.secret_key,
            secure=self.config.minio.use_ssl,
            region=self.config.minio.region,
        )
        self._sse = SseS3()  # Server-side encryption (AES-256)
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """Create the bucket if it doesn't exist, enable versioning."""
        bucket = self.config.minio.bucket_name
        try:
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket, self.config.minio.region)
                logger.info("Created MinIO bucket: %s", bucket)
        except S3Error as exc:
            logger.error("MinIO bucket setup failed: %s", exc)
            raise

    def upload_segment(
        self, segment: SegmentResult, org_id: str
    ) -> str:
        """Upload a video segment to MinIO.

        Uses the S3 key format: {org_id}/{camera_id}/{date}/{segment_id}.mp4
        Applies server-side encryption and sets metadata headers.

        Args:
            segment: Completed segment metadata.
            org_id: Organization ID for path namespacing.

        Returns:
            The S3 key of the uploaded object.

        Raises:
            FileNotFoundError: If the segment file doesn't exist.
            S3Error: On MinIO upload failure.
        """
        if not os.path.exists(segment.file_path):
            raise FileNotFoundError(
                f"Segment file not found: {segment.file_path}"
            )

        # Build S3 key with date-based partitioning
        from datetime import datetime, timezone
        date_str = datetime.fromtimestamp(
            segment.start_time, tz=timezone.utc
        ).strftime("%Y/%m/%d")
        s3_key = (
            f"{org_id}/{segment.camera_id}/{date_str}/"
            f"{segment.segment_id}{self.config.segment.output_extension}"
        )

        file_size = os.path.getsize(segment.file_path)

        # Metadata headers
        metadata = {
            "x-amz-meta-camera-id": segment.camera_id,
            "x-amz-meta-segment-id": segment.segment_id,
            "x-amz-meta-duration-ms": str(segment.duration_ms),
            "x-amz-meta-fps": str(segment.fps),
            "x-amz-meta-resolution": segment.resolution,
            "x-amz-meta-codec": segment.codec,
            "x-amz-meta-frame-count": str(segment.frame_count),
            "x-amz-meta-start-time": str(segment.start_time),
            "x-amz-meta-end-time": str(segment.end_time),
        }

        logger.info(
            "Uploading segment %s (%.1f KB) to %s",
            segment.segment_id, file_size / 1024, s3_key
        )

        # Use multipart upload for large files
        part_size = 0  # 0 = auto (default 5MB parts)
        if file_size > self.config.minio.multipart_threshold_mb * 1024 * 1024:
            part_size = 10 * 1024 * 1024  # 10MB parts

        self._client.fput_object(
            bucket_name=self.config.minio.bucket_name,
            object_name=s3_key,
            file_path=segment.file_path,
            content_type="video/mp4",
            metadata=metadata,
            sse=self._sse,
            part_size=part_size,
        )

        logger.info("Upload complete: %s", s3_key)
        return s3_key

    def upload_with_retry(
        self,
        segment: SegmentResult,
        org_id: str,
        max_retries: int = 3,
    ) -> str:
        """Upload a segment with exponential backoff retry.

        Args:
            segment: Completed segment metadata.
            org_id: Organization ID.
            max_retries: Maximum retry attempts.

        Returns:
            The S3 key of the uploaded object.

        Raises:
            S3Error: If all retries are exhausted.
        """
        last_error: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                return self.upload_segment(segment, org_id)
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    delay = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        "Upload failed for %s (attempt %d/%d), retrying in %ds: %s",
                        segment.segment_id, attempt + 1, max_retries, delay, exc
                    )
                    time.sleep(delay)

        logger.error(
            "Upload exhausted retries for segment %s: %s",
            segment.segment_id, last_error
        )
        raise last_error  # type: ignore[misc]

    def generate_presigned_url(
        self, s3_key: str, expires_s: int = 300
    ) -> str:
        """Generate a time-limited presigned URL for video playback.

        Args:
            s3_key: The object key in MinIO.
            expires_s: URL expiry in seconds (default 5 minutes).

        Returns:
            Presigned URL string.
        """
        from datetime import timedelta
        url = self._client.presigned_get_object(
            self.config.minio.bucket_name,
            s3_key,
            expires=timedelta(seconds=expires_s),
        )
        return url

    def delete_segment(self, s3_key: str) -> None:
        """Delete a video segment from MinIO.

        Args:
            s3_key: The object key to delete.
        """
        try:
            self._client.remove_object(
                self.config.minio.bucket_name, s3_key
            )
            logger.info("Deleted segment: %s", s3_key)
        except S3Error as exc:
            logger.error("Failed to delete segment %s: %s", s3_key, exc)
            raise

    def cleanup_local_file(self, file_path: str) -> None:
        """Remove a local segment file after successful upload."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info("Cleaned up local file: %s", file_path)
        except OSError as exc:
            logger.error("Failed to clean up local file %s: %s", file_path, exc)
