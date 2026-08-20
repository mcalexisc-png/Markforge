"""ZIP packaging of conversion results (markdown + assets)."""

from __future__ import annotations

import os
import uuid
import zipfile
from pathlib import Path

from app.services.storage import job_output_dir


def _newest_output_mtime(items: list[dict]) -> float:
    """Newest mtime across every completed result directory (0 when none)."""
    newest = 0.0
    for item in items:
        if item.get("status") != "completed" or not item.get("output_dir"):
            continue
        out_dir = Path(item["output_dir"])
        if not out_dir.exists():
            continue
        for path in out_dir.rglob("*"):
            if path.is_file():
                newest = max(newest, path.stat().st_mtime)
    return newest


def build_results_zip(job_id: str, items: list[dict]) -> Path:
    """Package every completed result into a single ZIP.

    Each result becomes ``<stem>/document.md`` plus its ``assets/`` folder,
    so the Markdown stays fully functional after download.

    The archive is written to a unique temp path and atomically renamed into
    place, so concurrent downloads can never read a half-written file. An
    existing archive is reused when it is newer than every packaged result.
    """
    output_root = job_output_dir(job_id)
    output_root.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"markforge-{job_id}.zip"
    if zip_path.exists() and zip_path.stat().st_mtime >= _newest_output_mtime(items):
        return zip_path

    tmp_path = output_root / f".markforge-{job_id}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in items:
                if item.get("status") != "completed" or not item.get("output_dir"):
                    continue
                out_dir = Path(item["output_dir"])
                if not out_dir.exists():
                    continue
                folder = out_dir.name
                for file in sorted(out_dir.rglob("*")):
                    if file.is_file():
                        archive.write(file, Path(folder) / file.relative_to(out_dir))
        os.replace(tmp_path, zip_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return zip_path