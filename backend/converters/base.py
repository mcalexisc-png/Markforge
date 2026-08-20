"""Converter base classes, shared context and errors.

All format converters implement :class:`BaseConverter` and emit a
:class:`Document` through a :class:`ConversionContext`, which owns asset
writing, progress reporting and warning collection.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from app.schemas.settings import ConversionSettings
from document_model.document import Document, DocumentStats
from document_model.metadata import normalize_metadata

ProgressCallback = Callable[[str, int, int, str], None]


class ConversionError(Exception):
    """A user-presentable conversion failure."""

    code = "conversion_failed"

    def __init__(self, message: str, *, code: str | None = None, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.detail = detail


class UnsupportedFormatError(ConversionError):
    code = "unsupported_format"


class CorruptFileError(ConversionError):
    code = "corrupt_file"


class OcrUnavailableError(ConversionError):
    code = "ocr_unavailable"


class ConversionTimeoutError(ConversionError):
    code = "conversion_timeout"


class ConversionContext:
    """Shared state for one file conversion inside a job."""

    def __init__(
        self,
        *,
        source_path: Path,
        settings: ConversionSettings,
        output_dir: Path,
        job_id: str = "local",
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        self.source_path = source_path
        self.settings = settings
        self.output_dir = output_dir
        self.asset_dir = output_dir / "assets"
        self.job_id = job_id
        self.progress_cb = progress_cb
        self.ocr_used = False
        self.ocr_texts: dict[int, str] = {}
        self.markdown_output: str | None = None
        self._seen_assets: dict[str, str] = {}

    def progress(self, phase: str, current: int = 0, total: int = 0, message: str = "") -> None:
        if self.progress_cb:
            self.progress_cb(phase, current, total, message)

    def save_image(self, data: bytes, ext: str, alt: str = "") -> str | None:
        """Write an extracted image to the assets directory (deduplicated).

        Returns the relative path (``assets/name.ext``) or None when there is
        no image data.
        """
        if not data:
            return None
        digest = hashlib.sha256(data).hexdigest()[:16]
        if digest in self._seen_assets:
            return self._seen_assets[digest]
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        ext = (ext or "png").lower().lstrip(".")
        if ext not in {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif"}:
            ext = "png"
        count = len(self._seen_assets) + 1
        name = f"image-{count:03d}.{ext}"
        (self.asset_dir / name).write_bytes(data)
        rel = f"assets/{name}"
        self._seen_assets[digest] = rel
        return rel


class BaseConverter(ABC):
    """Interface every format converter implements."""

    format: ClassVar[str] = "unknown"
    extensions: ClassVar[tuple[str, ...]] = ()

    def __init__(self, context: ConversionContext):
        self.context = context

    @classmethod
    def supports(cls, ext: str) -> bool:
        return ext.lower() in cls.extensions

    @abstractmethod
    def convert(self) -> Document:
        """Parse the source file and return a Document in the CDM."""

    def _build_document(self, metadata: dict) -> Document:
        return Document(
            format=self.format,
            filename=self.context.source_path.name,
            metadata=normalize_metadata(metadata),
            stats=DocumentStats(),
        )

    def warn(self, code: str, message: str, detail: str | None = None) -> None:
        self._last_doc.warnings.append(
            {"code": code, "message": message, "detail": detail, "severity": "warning"}
        )

    def _track(self, doc: Document) -> Document:
        self._last_doc = doc
        return doc
