"""Filesystem layout, upload/output storage and retention cleanup."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import settings


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


def run_retention(now: datetime | None = None) -> tuple[int, int]:
    """Delete finished job outputs older than the retention period.

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
        mtime = datetime.fromtimestamp(job_dir.stat().st_mtime, tz=UTC)
        if mtime < cutoff:
            freed += dir_size(job_dir)
            shutil.rmtree(job_dir, ignore_errors=True)
            deleted += 1
    return deleted, freed


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
