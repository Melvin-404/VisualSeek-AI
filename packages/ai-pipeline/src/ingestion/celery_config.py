"""Celery application configuration and initialization.

Configures the Celery broker, result backend, serialization,
task routing, and dead letter queue for failed ingestion tasks.
"""

from celery import Celery
from ingestion.config import IngestionConfig

config = IngestionConfig()

celery_app = Celery("visionquery-ingestion")

celery_app.conf.update(
    broker_url=config.celery.broker_url,
    result_backend=config.celery.result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=config.celery.task_acks_late,
    worker_prefetch_multiplier=config.celery.worker_prefetch_multiplier,
    task_soft_time_limit=config.celery.task_soft_time_limit,
    task_time_limit=config.celery.task_time_limit,
    # Task routing
    task_routes={
        "ingestion.tasks.ingest_camera_stream": {"queue": "gpu-worker"},
        "ingestion.tasks.process_segment": {"queue": "gpu-worker"},
    },
    # Dead letter queue for failed tasks
    task_reject_on_worker_lost=True,
    task_default_queue="default",
    # Retry policy
    task_annotations={
        "ingestion.tasks.process_segment": {
            "max_retries": 3,
            "default_retry_delay": 10,
        },
    },
)
