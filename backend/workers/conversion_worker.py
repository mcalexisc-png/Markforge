"""Celery conversion worker.

Each job runs inside its own isolated process; document content is never
logged and uploaded files are deleted after processing.
"""

from __future__ import annotations

import logging

from celery import Task

from app.core.logging import configure_logging
from app.services.jobs import process_job
from workers.celery_app import celery_app


class ConversionTask(Task):
    name = "markforge.process_job"
    ignore_result = True

    def run(self, job_id: str) -> None:
        configure_logging()
        logger = logging.getLogger("markforge.worker")
        logger.info("Worker processing job %s", job_id)
        process_job(job_id)


celery_app.register_task(ConversionTask())
