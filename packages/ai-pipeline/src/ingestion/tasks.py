"""Celery tasks for the video ingestion pipeline.

Defines the stream capture task and async segment processing (upload + DB entry).
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import task_failure
from sqlalchemy import create_engine, text

from ingestion.celery_config import celery_app
from ingestion.rtsp_worker import RTSPIngestionWorker
from ingestion.segmenter import SegmentResult
from ingestion.storage import MinIOVideoStorage

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="ingestion.tasks.ingest_camera_stream")
def ingest_camera_stream(self, camera_id: str, rtsp_url: str, org_id: str) -> None:
    """Long-running task to ingest a camera stream.

    Runs the RTSP worker capture loop, segments, and schedules processing tasks.
    """
    logger.info("Starting stream ingestion for camera: %s", camera_id)
    worker = RTSPIngestionWorker(camera_id, rtsp_url, org_id)

    try:
        worker.run()
    except SoftTimeLimitExceeded:
        logger.info("Soft time limit exceeded. Shutting down worker for camera %s", camera_id)
        worker.shutdown()
    except Exception as exc:
        logger.error("Worker failed for camera %s: %s", camera_id, exc)
        raise


@celery_app.task(bind=True, name="ingestion.tasks.process_segment", max_retries=3)
def process_segment(
    self, segment_path: str, camera_id: str, org_id: str, metadata: dict
) -> str:
    """Uploads segment to MinIO, creates DB record, and cleans up local file."""
    logger.info("Processing completed segment for camera %s, path: %s", camera_id, segment_path)

    segment_res = SegmentResult(
        file_path=segment_path,
        segment_id=metadata["segment_id"],
        camera_id=metadata["camera_id"],
        start_time=metadata["start_time"],
        end_time=metadata["end_time"],
        duration_ms=metadata["duration_ms"],
        fps=metadata["fps"],
        resolution=metadata["resolution"],
        codec=metadata["codec"],
        frame_count=metadata["frame_count"],
        file_size_bytes=metadata["file_size_bytes"],
    )

    storage = MinIOVideoStorage()

    try:
        # 1. Upload segment to MinIO
        s3_key = storage.upload_with_retry(segment_res, org_id)

        # 2. Record segment metadata in DB
        db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
        # Ensure we use psycopg2 for synchronous connection
        sync_db_url = db_url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")
        engine = create_engine(sync_db_url)

        query = text("""
            INSERT INTO video_segments (
                id, org_id, camera_id, s3_key, start_time, end_time, 
                duration_ms, fps, resolution, file_size_bytes, 
                processing_status, created_at, updated_at
            ) VALUES (
                :id, :org_id, :camera_id, :s3_key, :start_time, :end_time, 
                :duration_ms, :fps, :resolution, :file_size_bytes, 
                :processing_status, :created_at, :updated_at
            )
        """)

        now = datetime.now(timezone.utc)
        start_dt = datetime.fromtimestamp(segment_res.start_time, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(segment_res.end_time, tz=timezone.utc)

        with engine.connect() as conn:
            conn.execute(query, {
                "id": uuid.UUID(segment_res.segment_id),
                "org_id": uuid.UUID(org_id),
                "camera_id": uuid.UUID(segment_res.camera_id),
                "s3_key": s3_key,
                "start_time": start_dt,
                "end_time": end_dt,
                "duration_ms": segment_res.duration_ms,
                "fps": int(segment_res.fps),
                "resolution": segment_res.resolution,
                "file_size_bytes": segment_res.file_size_bytes,
                "processing_status": "pending",
                "created_at": now,
                "updated_at": now,
            })
            conn.commit()

        logger.info("Successfully processed segment %s and saved metadata to DB.", segment_res.segment_id)
        return s3_key

    except Exception as exc:
        logger.error("Error processing segment %s: %s", metadata.get("segment_id"), exc)
        try:
            self.retry(exc=exc, countdown=10)
        except Exception:
            raise exc
    finally:
        # 3. Clean up local file
        storage.cleanup_local_file(segment_path)


@task_failure.connect(sender=process_segment)
def handle_task_failure(sender, task_id, exception, args, kwargs, traceback, einfo, **extra) -> None:
    """Logs task failures to standard logger."""
    camera_id = kwargs.get("camera_id") or (args[1] if len(args) > 1 else "unknown")
    org_id = kwargs.get("org_id") or (args[2] if len(args) > 2 else "unknown")
    logger.error(
        "Ingestion task failure: task_id=%s, camera_id=%s, org_id=%s, exception=%s",
        task_id, camera_id, org_id, exception
    )
