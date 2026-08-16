"""ZIP packaging of conversion results (markdown + assets)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from app.services.storage import job_output_dir


def build_results_zip(job_id: str, items: list[dict]) -> Path:
    """Package every completed result into a single ZIP.

    Each result becomes ``<stem>/document.md`` plus its ``assets/`` folder,
    so the Markdown stays fully functional after download.
    """
    output_root = job_output_dir(job_id)
    zip_path = output_root / f"markforge-{job_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
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
    return zip_path
