"""Job endpoints: create, poll, preview, download, delete, history."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import settings
from app.core.security import safe_filename
from app.schemas.job import HistoryItem, JobCreate, JobOut, MarkdownUpdate, PreviewOut
from app.services import jobs as job_service
from app.services import search
from app.services.zip_service import build_results_zip

logger = logging.getLogger("markforge.events")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# How often the stream re-reads job state. Progress is persisted to SQLite
# by the conversion callback, so this is the resolution of the push, not a
# client-side poll: one reader per stream instead of one request per second
# per browser tab.
_EVENT_TICK = 0.4
# Terminal states end the stream; there is nothing further to report.
_TERMINAL = {"completed", "partial", "failed"}
# A comment line keeps proxies from closing an idle connection.
_KEEPALIVE_AFTER = 15.0


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
        # Prefer the size recorded at completion. Only fall back to walking the
        # directory for results converted before that was stored -- otherwise
        # every poll of this endpoint rglobs every job's output.
        output_size = 0
        for item in job.items:
            if item.output_size:
                output_size += item.output_size
            elif item.output_dir:
                out_dir = Path(item.output_dir)
                if out_dir.exists():
                    output_size += sum(
                        f.stat().st_size for f in out_dir.rglob("*") if f.is_file()
                    )
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
async def create_job(payload: JobCreate) -> JobOut:
    if len(payload.file_ids) > settings.max_files_per_job:
        raise HTTPException(
            status_code=400,
            detail=f"A job can contain at most {settings.max_files_per_job} files.",
        )
    try:
        job = job_service.create_job(payload.file_ids, payload.settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        job_service.dispatch_job(job.id)
    except (job_service.QueueFullError, job_service.ConversionCapacityError) as exc:
        # The row is already committed. Without this it would sit in the
        # database as permanently "queued" -- and retention only reaps
        # terminal jobs, so its output directory would be kept forever.
        job_service.delete_job(job.id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return job_service.to_job_out(job)


@router.get("", response_model=list[JobOut])
async def list_jobs(limit: int = Query(default=25, le=100)) -> list[JobOut]:
    return job_service.list_jobs(limit=limit)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str) -> JobOut:
    return _require_job(job_id)


@router.get("/{job_id}/status", response_model=JobOut)
async def job_status(job_id: str) -> JobOut:
    """Deprecated alias of ``GET /api/jobs/{job_id}``.

    Kept so existing callers do not break; it returns the identical payload
    rather than duplicating the handler body.
    """
    return _require_job(job_id)


def _require_item(job, file_id: str | None):
    """Resolve a job's file, defaulting to the first when none is named."""
    if not file_id:
        return job.items[0]
    item = next((i for i in job.items if i.file_id == file_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="File not found in job.")
    return item


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    """Stream job progress as Server-Sent Events until the job finishes.

    Replaces per-second polling from every open tab. The payload is the same
    ``JobOut`` the poll endpoint returns, so the client renders it unchanged.
    """
    _require_job(job_id)

    async def event_stream():
        last_payload: str | None = None
        idle = 0.0
        try:
            while True:
                if await request.is_disconnected():
                    break

                job = await asyncio.to_thread(job_service.get_job, job_id)
                if job is None:
                    yield "event: gone\ndata: {}\n\n"
                    break

                out = job_service.to_job_out(job)
                payload = json.dumps(out.model_dump(mode="json"))

                if payload != last_payload:
                    last_payload = payload
                    idle = 0.0
                    yield f"event: job\ndata: {payload}\n\n"
                else:
                    idle += _EVENT_TICK
                    if idle >= _KEEPALIVE_AFTER:
                        idle = 0.0
                        yield ": keepalive\n\n"

                if out.status in _TERMINAL:
                    yield "event: done\ndata: {}\n\n"
                    break

                await asyncio.sleep(_EVENT_TICK)
        except asyncio.CancelledError:  # client went away mid-send
            raise
        except Exception:
            logger.exception("Event stream failed for job %s", job_id)
            yield "event: error\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Tell nginx and friends not to buffer, or events arrive in a clump
            # at the end and the stream is pointless.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/preview", response_model=PreviewOut)
async def job_preview(job_id: str, file_id: str | None = None) -> PreviewOut:
    job = _require_job(job_id)
    item = _require_item(job, file_id)
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
    item = _require_item(job, file_id)
    if item.status != "completed" or not item.output_dir:
        raise HTTPException(status_code=409, detail="This file has no result yet.")
    output_dir = Path(item.output_dir)
    markdown_path = output_dir / (item.markdown_filename or "document.md")
    original_path = output_dir / "document.original.md"
    source = original_path if original_path.exists() else markdown_path
    content = source.read_text(encoding="utf-8")
    markdown_path.write_text(content, encoding="utf-8")
    search.index_document(job_id, item.file_id, item.filename, content)
    job_service.reset_edited(job_id, item.file_id)
    return PreviewOut(
        job_id=job_id,
        filename=item.filename,
        content=content,
        stats=item.stats,
        warnings=item.warnings,
        ocr_used=item.ocr_used,
    )


@router.api_route("/{job_id}/download", methods=["GET", "HEAD"])
async def job_download(job_id: str, file_id: str | None = None) -> FileResponse:
    job = _require_job(job_id)
    item = _require_item(job, file_id)
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


@router.api_route("/{job_id}/zip", methods=["GET", "HEAD"])
def job_zip(job_id: str) -> FileResponse:
    job = _require_job(job_id)
    if job.status not in ("completed", "partial"):
        raise HTTPException(
            status_code=409,
            detail="The job is still running; results are not ready to package.",
        )
    if not any(i.status == "completed" for i in job.items):
        raise HTTPException(status_code=409, detail="No completed results to package.")
    zip_path = build_results_zip(job_id, [i.model_dump() for i in job.items])
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"markforge-{job_id}.zip",
    )


@router.get("/{job_id}/assets/{file_id}/{name}")
async def job_asset(job_id: str, file_id: str, name: str) -> FileResponse:
    """Serve one extracted figure so the in-app preview can render it.

    The stored Markdown keeps relative ``assets/...`` paths so a downloaded ZIP
    stays portable; only the rendered preview points at this route.
    """
    job = _require_job(job_id)
    item = _require_item(job, file_id)
    if not item.output_dir:
        raise HTTPException(status_code=404, detail="Asset not found.")

    safe_name = safe_filename(name)
    asset_dir = (Path(item.output_dir) / "assets").resolve()
    target = (asset_dir / safe_name).resolve()
    # Containment check: never serve anything outside this file's asset dir,
    # whatever the name decoded to.
    if not target.is_relative_to(asset_dir) or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found.")

    media_type, _ = mimetypes.guess_type(target.name)
    if not media_type or not media_type.startswith("image/"):
        raise HTTPException(status_code=404, detail="Asset not found.")

    return FileResponse(
        target,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str) -> None:
    if job_service.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    job_service.delete_job(job_id)
