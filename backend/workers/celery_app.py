"""Celery application for background conversion jobs."""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "markforge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.conversion_worker"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_soft_time_limit=max(60, settings.job_timeout),
    task_time_limit=max(120, settings.job_timeout + 60),
    worker_max_tasks_per_child=50,
    task_reject_on_worker_lost=True,
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
)
