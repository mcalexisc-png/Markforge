"""File upload endpoint: validation, deduplication, safe storage."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, UploadFile

from app.core.db import SessionLocal
from app.models.job import UploadedFile
from app.schemas.job import UploadedFile as UploadedFileOut
from app.services.files import UploadValidationError, store_upload, validate_upload
from app.services.storage import job_upload_dir as upload_dir

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload", response_model=list[UploadedFileOut])
async def upload_files(files: list[UploadFile]) -> list[UploadedFileOut]:
    """Upload one or more documents for a conversion job."""
    records: list[UploadedFileOut] = []
    db = SessionLocal()
    try:
        for file in files:
            filename = file.filename or ""
            data = await file.read()
            try:
                validate_upload(filename, len(data), data)
            except UploadValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            from app.core.security import sha256_of_bytes

            digest = sha256_of_bytes(data)
            existing = db.query(UploadedFile).filter(UploadedFile.sha256 == digest).first()
            existing_path = None
            if existing is not None:
                candidate = upload_dir(existing.id) / existing.name
                existing_path = candidate if candidate.exists() else None
            if existing_path is not None:
                records.append(
                    UploadedFileOut(
                        id=existing.id,
                        name=existing.name,
                        size=existing.size,
                        format=existing.format,
                        sha256=existing.sha256,
                        duplicate_of=existing.id,
                    )
                )
                continue

            file_id = uuid.uuid4().hex[:12]
            record = store_upload(file_id, filename, data)
            row = UploadedFile(
                id=record["id"],
                name=record["name"],
                size=record["size"],
                format=record["format"],
                sha256=record["sha256"],
            )
            db.add(row)
            db.commit()
            records.append(UploadedFileOut(**record))
    finally:
        db.close()
    return records
