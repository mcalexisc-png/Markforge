"""API response schemas for files, jobs and health."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UploadedFile(BaseModel):
    id: str
    name: str
    size: int
    format: str
    sha256: str
    duplicate_of: str | None = None


class FileReference(BaseModel):
    id: str
    name: str
    size: int
    format: str


class JobFileState(BaseModel):
    file_id: str
    filename: str
    format: str
    status: Literal["queued", "running", "completed", "failed", "skipped"] = "queued"
    progress: float = 0.0
    phase: str = "Queued"
    message: str = ""
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
    output_dir: str | None = None
    markdown_filename: str | None = None
    ocr_used: bool = False
    edited: bool = False
    error: dict[str, Any] | None = None


class JobOut(BaseModel):
    id: str
    status: str
    progress: float
    phase: str
    files: list[FileReference]
    items: list[JobFileState]
    settings: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, str] | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobCreate(BaseModel):
    file_ids: list[str] = Field(min_length=1)
    settings: dict[str, Any] = Field(default_factory=dict)


class PreviewOut(BaseModel):
    job_id: str
    filename: str
    content: str
    stats: dict[str, int]
    warnings: list[dict[str, Any]]
    ocr_used: bool


class MarkdownUpdate(BaseModel):
    content: str = Field(min_length=0, max_length=100_000_000)
    file_id: str | None = None


class HistoryItem(BaseModel):
    id: str
    filename: str
    format: str
    status: str
    created_at: datetime
    finished_at: datetime | None = None
    output_size: int = 0
    warning_count: int = 0
    stats: dict[str, int] = Field(default_factory=dict)


class HealthOut(BaseModel):
    status: str
    version: str = "1.0.0"
    redis: str
    worker: str
    storage: str
    lan: dict[str, Any] = Field(default_factory=dict)


class VerifyIn(BaseModel):
    password: str
