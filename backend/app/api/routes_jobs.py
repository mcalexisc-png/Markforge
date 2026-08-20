"""Job endpoints: create, poll, preview, download, delete, history."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.job import HistoryItem, JobCreate, JobOut, MarkdownUpdate, PreviewOut
from app.services import jobs as job_service
from app.services.zip_service import build_results_zip

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _require_job(job_id: str) -> JobOut:
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job_service.to_job_out(job)


@router.get("/history", response_model=list[HistoryItem])
async def job_history(limit: int = Query(default=25, le=100)) -> list[HistoryItem]:
    jobs = job_service.list_jobs(limit=limit)
    items: list[HistoryItem] = []
    for job in jobs:
        if not job.files:
            continue
        warnings = sum(len(i.warnings) for i in job.items)
        output_size = 0
        for item in job.items:
            if item.output_dir:
                out_dir = Path(item.output_dir)
                if out_dir.exists():
                    output_size += sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())
        items.append(
            HistoryItem(
                id=job.id,
                filename=job.files[0].name if len(job.files) == 1 else f"{len(job.files)} files",
                format=",".join({f.format for f in job.files}),
                status=job.status,
                created_at=job.created_at,
                finished_at=job.finished_at,
                output_size=output_size,
                warning_count=warnings,
                stats=job.items[0].stats if job.items else {},
            )
        )
    return items


@router.post("", response_model=JobOut, status_code=201)
async def create_job(payload: JobCreate, background: BackgroundTasks) -> JobOut:
    if len(payload.file_ids) > settings.max_files_per_job:
        raise HTTPException(
            status_code=400,
            detail=f"A job can contain at most {settings.max_files_per_job} files.",
        )
    try:
        job = job_service.create_job(payload.file_ids, payload.settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_service.dispatch_job(job.id)
    return job_service.to_job_out(job)


@router.get("", response_model=list[JobOut])
async def list_jobs(limit: int = Query(default=25, le=100)) -> list[JobOut]:
    return job_service.list_jobs(limit=limit)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str) -> JobOut:
    return _require_job(job_id)


@router.get("/{job_id}/status", response_model=JobOut)
async def job_status(job_id: str) -> JobOut:
    return _require_job(job_id)


@router.get("/{job_id}/preview", response_model=PreviewOut)
async def job_preview(job_id: str, file_id: str | None = None) -> PreviewOut:
    job = _require_job(job_id)
    item = job.items[0]
    if file_id:
        item = next((i for i in job.items if i.file_id == file_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="File not found in job.")
    if item.status != "completed" or not item.output_dir:
        raise HTTPException(status_code=409, detail="This file has no result yet.")
    markdown_path = Path(item.output_dir) / (item.markdown_filename or "document.md")
    if not markdown_path.exists():
        raise HTTPException(status_code=404, detail="Result file missing.")
    return PreviewOut(
        job_id=job_id,
        filename=item.filename,
        content=markdown_path.read_text(encoding="utf-8"),
        stats=item.stats,
        warnings=item.warnings,
        ocr_used=item.ocr_used,
    )


@router.put("/{job_id}/markdown", status_code=204)
async def save_markdown(job_id: str, payload: MarkdownUpdate) -> None:
    _require_job(job_id)
    try:
        job_service.save_markdown(job_id, payload.file_id, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{job_id}/reset", response_model=PreviewOut)
async def reset_markdown(job_id: str, file_id: str | None = None) -> PreviewOut:
    """Restore the original extraction, discarding any edits."""
    job = _require_job(job_id)
    item = job.items[0]
    if file_id:
        item = next((i for i in job.items if i.file_id == file_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="File not found in job.")
    if item.status != "completed" or not item.output_dir:
        raise HTTPException(status_code=409, detail="This file has no result yet.")
    output_dir = Path(item.output_dir)
    markdown_path = output_dir / (item.markdown_filename or "document.md")
    original_path = output_dir / "document.original.md"
    source = original_path if original_path.exists() else markdown_path
    content = source.read_text(encoding="utf-8")
    markdown_path.write_text(content, encoding="utf-8")
    job_service.reset_edited(job_id, item.file_id)
    return PreviewOut(
        job_id=job_id,
        filename=item.filename,
        content=content,
        stats=item.stats,
        warnings=item.warnings,
        ocr_used=item.ocr_used,
    )


@router.get("/{job_id}/download")
async def job_download(job_id: str, file_id: str | None = None) -> FileResponse:
    job = _require_job(job_id)
    item = job.items[0]
    if file_id:
        item = next((i for i in job.items if i.file_id == file_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="File not found in job.")
    if item.status != "completed" or not item.output_dir:
        raise HTTPException(status_code=409, detail="This file has no result yet.")
    markdown_path = Path(item.output_dir) / (item.markdown_filename or "document.md")
    if not markdown_path.exists():
        raise HTTPException(status_code=404, detail="Result file missing.")
    download_name = Path(item.filename).stem + ".md"
    return FileResponse(
        markdown_path,
        media_type="text/markdown; charset=utf-8",
        filename=download_name,
    )


@router.get("/{job_id}/zip")
async def job_zip(job_id: str) -> FileResponse:
    job = _require_job(job_id)
    if not any(i.status == "completed" for i in job.items):
        raise HTTPException(status_code=409, detail="No completed results to package.")
    zip_path = build_results_zip(job_id, [i.model_dump() for i in job.items])
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"markforge-{job_id}.zip",
    )


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str) -> None:
    if job_service.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    job_service.delete_job(job_id)
