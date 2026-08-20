"""Job orchestration: creation, dispatch, synchronous execution pipeline.

The pipeline is identical whether a job runs in-process (sync mode) or in a
Celery worker. Progress is persisted to SQLite so either runner can be used
and the frontend polls the same endpoint.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import safe_stem
from app.models.job import Job, UploadedFile
from app.schemas.job import JobFileState, JobOut
from app.schemas.settings import ConversionSettings
from app.services import storage
from app.services.storage import job_output_dir, job_upload_dir
from converters.base import ConversionContext, ConversionError
from markdown.cleanup import postprocess

logger = logging.getLogger("markforge.jobs")

_job_slots = threading.BoundedSemaphore(max(1, settings.max_concurrent_jobs))

_MIN_TIMEOUT = 30


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# --------------------------------------------------------------------- #
# Creation & persistence helpers
# --------------------------------------------------------------------- #


def create_job(file_ids: list[str], settings_dict: dict) -> Job:
    db = SessionLocal()
    try:
        files = (
            db.query(UploadedFile).filter(UploadedFile.id.in_(file_ids)).all()
        )
        by_id = {f.id: f for f in files}
        missing = [fid for fid in file_ids if fid not in by_id]
        if missing:
            raise ValueError(f"Unknown uploaded files: {missing}")

        job_id = storage.new_job_id()
        converted_settings = ConversionSettings(**settings_dict)
        job = Job(
            id=job_id,
            status="queued",
            progress=0.0,
            phase="Queued",
            files_json=json.dumps(
                [
                    {
                        "id": f.id,
                        "name": f.name,
                        "size": f.size,
                        "format": f.format,
                        "sha256": f.sha256,
                    }
                    for f in files
                ]
            ),
            items_json=json.dumps(
                [
                    {
                        "file_id": f.id,
                        "filename": f.name,
                        "format": f.format,
                        "status": "queued",
                        "progress": 0.0,
                        "phase": "Queued",
                        "message": "",
                        "warnings": [],
                        "stats": {},
                        "output_dir": None,
                        "markdown_filename": None,
                        "ocr_used": False,
                        "error": None,
                    }
                    for f in files
                ]
            ),
            settings_json=json.dumps(converted_settings.model_dump()),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job
    finally:
        db.close()


def get_job(job_id: str) -> Job | None:
    db = SessionLocal()
    try:
        return db.get(Job, job_id)
    finally:
        db.close()


def to_job_out(job: Job) -> JobOut:
    files = json.loads(job.files_json or "[]")
    items = json.loads(job.items_json or "[]")
    error = json.loads(job.error_json) if job.error_json else None
    return JobOut(
        id=job.id,
        status=job.status,
        progress=job.progress,
        phase=job.phase,
        files=[
            {
                "id": f.get("id", ""),
                "name": f.get("name", "file"),
                "size": f.get("size", 0),
                "format": f.get("format", ""),
            }
            for f in files
        ],
        items=[JobFileState(**item) for item in items],
        settings=json.loads(job.settings_json or "{}"),
        error=error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def dispatch_job(job_id: str) -> None:
    """Queue the job through Celery when configured, otherwise run inline."""
    if settings.job_mode == "celery":
        from workers.celery_app import celery_app

        celery_app.send_task("markforge.process_job", args=[job_id])
        logger.info("Dispatched job %s to Celery", job_id)
    else:
        if not _job_slots.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail="Too many conversions are already running. Please wait a moment and try again.",
            )
        threading.Thread(target=_run_job_with_slot, args=[job_id], daemon=True).start()
        logger.info("Dispatched job %s in-process", job_id)


def _run_job_with_slot(job_id: str) -> None:
    try:
        process_job(job_id)
    finally:
        _job_slots.release()


# --------------------------------------------------------------------- #
# Execution pipeline (shared by sync runner and Celery worker)
# --------------------------------------------------------------------- #


def process_job(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        logger.error("Job %s not found for processing", job_id)
        return

    db = SessionLocal()
    try:
        tracked = db.get(Job, job_id)
        if tracked is None:
            return
        items = json.loads(tracked.items_json or "[]")
        tracked.status = "running"
        tracked.started_at = _now()
        _save_job(db, tracked, items)
    finally:
        db.close()

    started = datetime.now()
    completed = 0
    failed = 0
    settings_dict = json.loads(job.settings_json or "{}")
    used_stems: set[str] = set()

    for item in items:
        item_status = _process_item(job_id, item, settings_dict, used_stems)
        if item_status == "completed":
            completed += 1
        else:
            failed += 1

    final_status = "failed"
    db = SessionLocal()
    try:
        tracked = db.get(Job, job_id)
        if tracked is None:
            return
        final_items = json.loads(tracked.items_json or "[]")
        if failed == 0 and completed == len(final_items):
            tracked.status = "completed"
        elif completed > 0:
            tracked.status = "partial"
        else:
            tracked.status = "failed"
        tracked.progress = 100.0 if tracked.status == "completed" else tracked.progress
        tracked.phase = "Completed" if tracked.status in ("completed", "partial") else "Failed"
        tracked.finished_at = _now()
        final_status = tracked.status
        _save_job(db, tracked, final_items)
        # Originals are no longer needed once processing is done.
        for item in final_items:
            cleanup_upload(item["file_id"], exclude_job=job_id)
    except Exception:
        logger.exception("Failed to finalize job %s", job_id)
    finally:
        db.close()

    elapsed = (datetime.now() - started).total_seconds()
    logger.info(
        "Job %s finished: %s (%d ok, %d failed) in %.1fs",
        job_id,
        final_status,
        completed,
        failed,
        elapsed,
    )


def _process_item(job_id: str, item: dict, settings_dict: dict, used_stems: set[str] | None = None) -> str:
    file_id = item["file_id"]
    filename = item["filename"]
    conversion_settings = ConversionSettings(**settings_dict)

    output_root = job_output_dir(job_id)
    stem = safe_stem(filename)
    if used_stems is not None:
        base = stem
        counter = 2
        while stem in used_stems:
            stem = f"{base}-{counter}"
            counter += 1
        used_stems.add(stem)
    output_dir = output_root / stem
    output_dir.mkdir(parents=True, exist_ok=True)
    item["output_dir"] = str(output_dir)

    source_path = job_upload_dir(file_id) / filename
    if not source_path.exists():
        item["status"] = "failed"
        item["error"] = {"code": "file_missing", "message": "The uploaded file is no longer available."}
        _update_item(job_id, item)
        return "failed"

    def progress_cb(phase: str, current: int, total: int, message: str) -> None:
        item["phase"] = message or phase
        if total > 0:
            item["progress"] = round(current / total * 100, 1)
        _update_item(job_id, item)

    context = ConversionContext(
        source_path=source_path,
        settings=conversion_settings,
        output_dir=output_dir,
        job_id=job_id,
        progress_cb=progress_cb,
    )

    item["status"] = "running"
    item["phase"] = "Starting"
    item["progress"] = 2.0
    _update_item(job_id, item)

    try:
        document = _convert_markitdown(context)
        markdown = context.markdown_output or ""
        markdown = postprocess(markdown, output_mode=conversion_settings.output_mode)

        markdown_path = output_dir / "document.md"
        markdown_path.write_text(markdown, encoding="utf-8")

        original_path = output_dir / "document.original.md"
        if not original_path.exists():
            original_path.write_text(markdown, encoding="utf-8")

        warnings = [w for w in document.warnings if isinstance(w, dict)] or [
            {"code": w.code, "message": w.message, "detail": w.detail, "severity": w.severity}
            for w in document.warnings
        ]
        item["warnings"] = warnings
        item["stats"] = document.stats.model_dump()
        item["status"] = "completed"
        item["progress"] = 100.0
        item["phase"] = "Completed"
        item["markdown_filename"] = "document.md"
        item["ocr_used"] = context.ocr_used
        _update_item(job_id, item)
        return "completed"
    except FutureTimeout:
        item["status"] = "failed"
        item["error"] = {
            "code": "timeout",
            "message": "The conversion exceeded the time limit and was stopped.",
        }
        _update_item(job_id, item)
        return "failed"
    except ConversionError as exc:
        item["status"] = "failed"
        item["error"] = {"code": exc.code, "message": exc.message, "detail": exc.detail}
        _update_item(job_id, item)
        return "failed"
    except Exception:  # never let one file take down the job
        logger.exception("Unexpected conversion failure for %s", filename)
        item["status"] = "failed"
        item["error"] = {
            "code": "conversion_failed",
            "message": "We couldn't extract the contents of this file.",
        }
        _update_item(job_id, item)
        return "failed"


def _convert_markitdown(context: ConversionContext):
    """Run the MarkItDown engine, aborting after the configured timeout."""
    from converters.markitdown import convert_with_markitdown

    return _run_with_timeout(lambda: convert_with_markitdown(context))


def _run_with_timeout(fn):
    """Execute ``fn`` in a worker thread, aborting after the configured timeout.

    A timed-out thread cannot be killed; it is simply abandoned (the job is
    marked failed) and its executor is shut down without waiting so the
    caller never blocks on the hung conversion.
    """
    timeout = max(_MIN_TIMEOUT, settings.job_timeout)

    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout:
        future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        pool.shutdown(wait=False)


# --------------------------------------------------------------------- #
# State updates
# --------------------------------------------------------------------- #


def _update_item(job_id: str, item: dict) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        items = json.loads(job.items_json or "[]")
        for index, existing in enumerate(items):
            if existing["file_id"] == item["file_id"]:
                items[index] = item
                break
        else:
            items.append(item)
        done = [i for i in items if i["status"] in ("completed", "failed")]
        job.progress = round(sum(i["progress"] for i in items) / max(len(items), 1), 1)
        running = next((i for i in items if i["status"] == "running"), None)
        job.phase = running["phase"] if running else (job.phase if done else "Queued")
        job.items_json = json.dumps(items, ensure_ascii=False)
        db.commit()
    finally:
        db.close()


def _save_job(db, job: Job, items: list[dict]) -> None:
    job.items_json = json.dumps(items, ensure_ascii=False)
    db.commit()


def cleanup_upload(file_id: str, *, exclude_job: str | None = None) -> None:
    """Delete an uploaded original unless another recent job references it."""
    from datetime import timedelta

    db = SessionLocal()
    try:
        cutoff = _now() - timedelta(hours=24)
        recent_jobs = db.query(Job).filter(Job.created_at >= cutoff).all()
        for job in recent_jobs:
            if exclude_job and job.id == exclude_job:
                continue
            try:
                referenced = {f["id"] for f in json.loads(job.files_json or "[]")}
            except (ValueError, TypeError):
                referenced = set()
            if file_id in referenced:
                return
    finally:
        db.close()
    shutil.rmtree(job_upload_dir(file_id), ignore_errors=True)


def save_markdown(job_id: str, file_id: str | None, content: str) -> None:
    """Write edited Markdown back to the job's output directory."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError("Job not found.")
        items = json.loads(job.items_json or "[]")
        item = None
        if file_id:
            item = next((i for i in items if i["file_id"] == file_id), None)
            if item is None:
                raise ValueError("File not found in job.")
        else:
            item = next((i for i in items if i.get("status") == "completed"), None)
        if item is None:
            raise ValueError("File not found in job.")
        if item.get("status") != "completed" or not item.get("output_dir"):
            raise ValueError("This file has no result yet.")
        markdown_path = Path(item["output_dir"]) / (item.get("markdown_filename") or "document.md")
        if not markdown_path.exists():
            raise ValueError("Result file missing.")
        markdown_path.write_text(content, encoding="utf-8")
        item["edited"] = True
        job.items_json = json.dumps(items, ensure_ascii=False)
        db.commit()
    finally:
        db.close()


def reset_edited(job_id: str, file_id: str) -> None:
    """Clear the edited flag after a reset (content is restored by the route)."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        items = json.loads(job.items_json or "[]")
        for existing in items:
            if existing["file_id"] == file_id:
                existing["edited"] = False
                break
        job.items_json = json.dumps(items, ensure_ascii=False)
        db.commit()
    finally:
        db.close()


def delete_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            db.delete(job)
            db.commit()
    finally:
        db.close()
    storage.delete_job_storage(job_id)


def list_jobs(limit: int = 50) -> list[JobOut]:
    db = SessionLocal()
    try:
        jobs = db.query(Job).order_by(Job.created_at.desc()).limit(limit).all()
        return [to_job_out(j) for j in jobs]
    finally:
        db.close()
