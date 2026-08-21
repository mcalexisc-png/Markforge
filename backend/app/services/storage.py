"""Filesystem layout, upload/output storage and retention cleanup."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import settings
from app.core.db import SessionLocal
from app.models.job import Job, UploadedFile
from app.services import search


def ensure_dirs() -> None:
    for path in (
        settings.resolve_upload_dir(),
        settings.resolve_output_dir(),
        settings.resolve_temp_dir(),
    ):
        path.mkdir(parents=True, exist_ok=True)


def job_upload_dir(job_id: str) -> Path:
    path = settings.resolve_upload_dir() / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_upload_path(job_id: str, filename: str) -> Path:
    return job_upload_dir(job_id) / filename


def job_output_dir(job_id: str) -> Path:
    path = settings.resolve_output_dir() / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_temp_dir(job_id: str) -> Path:
    path = settings.resolve_temp_dir() / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def delete_job_storage(job_id: str) -> None:
    """Remove all on-disk data associated with a job."""
    for base in (
        settings.resolve_upload_dir(),
        settings.resolve_output_dir(),
        settings.resolve_temp_dir(),
    ):
        shutil.rmtree(base / job_id, ignore_errors=True)


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _job_is_terminal(job_id: str) -> bool:
    """A job is safe to delete only when it is finished (or no longer tracked)."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return True
        return job.status in ("completed", "partial", "failed")
    finally:
        db.close()


def _newest_mtime(root: Path) -> datetime:
    """Newest modification time across a directory and all its files.

    Editing ``document.md`` refreshes the file but not the parent directory,
    so retention must look at descendants or it can delete output the user is
    still working on.
    """
    newest = root.stat().st_mtime
    for entry in root.rglob("*"):
        try:
            newest = max(newest, entry.stat().st_mtime)
        except OSError:
            continue
    return datetime.fromtimestamp(newest, tz=UTC)


def run_retention(now: datetime | None = None) -> tuple[int, int]:
    """Delete finished job outputs older than the retention period.

    Outputs belonging to queued or running jobs are always kept, as are
    outputs whose newest file (e.g. an edited ``document.md``) is recent.

    Returns (deleted_output_dirs, freed_bytes).
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=max(1, settings.retention_period))
    output_root = settings.resolve_output_dir()
    freed = 0
    deleted = 0
    for job_dir in output_root.iterdir() if output_root.exists() else []:
        if not job_dir.is_dir():
            continue
        if not _job_is_terminal(job_dir.name):
            continue
        if _newest_mtime(job_dir) < cutoff:
            freed += dir_size(job_dir)
            shutil.rmtree(job_dir, ignore_errors=True)
            # The index points at files that no longer exist; drop it with them
            # or search will return hits that cannot be opened.
            search.remove_job(job_dir.name)
            deleted += 1
    prune_uploaded_files()
    return deleted, freed


def prune_uploaded_files() -> int:
    """Drop upload rows whose originals no longer exist on disk.

    ``cleanup_upload`` removes the files but not the rows, so they would
    accumulate forever; rows for files still on disk are kept so re-uploads
    can be deduplicated.
    """
    db = SessionLocal()
    try:
        referenced: set[str] = set()
        for job in db.query(Job).all():
            try:
                referenced.update(f["id"] for f in json.loads(job.files_json or "[]"))
            except (ValueError, TypeError):
                continue
        upload_root = settings.resolve_upload_dir()
        removed = 0
        for row in db.query(UploadedFile).all():
            if row.id in referenced:
                continue
            if not (upload_root / row.id).exists():
                db.delete(row)
                removed += 1
        db.commit()
        return removed
    finally:
        db.close()


def cleanup_temp(now: datetime | None = None) -> int:
    """Remove temp directories older than 1 day."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=1)
    temp_root = settings.resolve_temp_dir()
    removed = 0
    for item in temp_root.iterdir() if temp_root.exists() else []:
        if item.is_dir():
            mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=UTC)
            if mtime < cutoff:
                shutil.rmtree(item, ignore_errors=True)
                removed += 1
    return removed


def storage_status() -> dict:
    """Report whether the storage locations are writable."""
    try:
        ensure_dirs()
        probe = settings.resolve_temp_dir() / f".probe-{uuid.uuid4().hex[:8]}"
        probe.write_text("ok")
        probe.unlink()
        writable = True
    except OSError:
        writable = False
    return {"writable": writable}
