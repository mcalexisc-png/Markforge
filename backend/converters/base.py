"""Shared conversion context and errors.

The MarkItDown adapter drives conversion; this module supplies the
:class:`ConversionContext` it runs against, which owns asset writing,
progress reporting and the resulting Markdown.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from app.schemas.settings import ConversionSettings

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
        # How many distinct images were recurring page-template chrome
        # (backgrounds/logos on most pages) and were kept on their first page
        # only. Set by extract_pdf_images; read back by convert_with_markitdown
        # to report it as a warning.
        self.recurring_backgrounds_suppressed = 0

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
