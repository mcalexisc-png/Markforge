"""Upload validation: extension, magic bytes, size limits, safe names."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.security import safe_filename, sha256_of_bytes
from app.services.storage import job_upload_dir
from converters.registry import ALLOWED_EXTENSIONS

_SIGNS: list[tuple[str, bytes]] = [
    ("pdf", b"%PDF"),
    ("zip", b"PK\x03\x04"),
]


def _magic_format(header: bytes) -> str | None:
    for fmt, sig in _SIGNS:
        if header.startswith(sig):
            return fmt
    return None


def _zip_kind(first_bytes: bytes) -> str:
    """Distinguish docx/pptx/xlsx archives by their content types."""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(first_bytes)) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return "zip"
    if any(n.startswith("xl/") for n in names):
        return "xlsx"
    if any(n.startswith("ppt/") for n in names):
        return "pptx"
    if any(n.startswith("word/") for n in names):
        return "docx"
    return "zip"


class UploadValidationError(ValueError):
    def __init__(self, message: str, code: str = "invalid_file"):
        super().__init__(message)
        self.code = code


def validate_upload(filename: str, size: int, first_bytes: bytes) -> str:
    """Validate an upload and return its detected format."""
    if not filename or "\x00" in filename:
        raise UploadValidationError("The file has an invalid name.", "invalid_filename")

    ext = Path(filename).suffix.lower()
    if not ext or ext not in ALLOWED_EXTENSIONS:
        supported = ", ".join(ext.lstrip(".") for ext in ALLOWED_EXTENSIONS)
        raise UploadValidationError(
            f"Unsupported file type. Markforge supports {supported} files.",
            "unsupported_type",
        )

    if size > settings.max_file_size:
        mb = settings.max_file_size // (1024 * 1024)
        raise UploadValidationError(
            f"This file exceeds the {mb} MB size limit.", "file_too_large"
        )

    declared = ext.lstrip(".")
    magic = _magic_format(first_bytes)
    if magic is None:
        raise UploadValidationError(
            f"This file does not look like a .{declared} document.",
            "not_a_document",
        )
    if declared == "pdf":
        if magic != "pdf":
            raise UploadValidationError(
                "The file extension (.pdf) does not match the file content.",
                "mime_mismatch",
            )
    else:
        if magic != "zip":
            raise UploadValidationError(
                f"This file does not look like a .{declared} archive.",
                "not_an_archive",
            )
        kind = _zip_kind(first_bytes)
        if kind != declared:
            raise UploadValidationError(
                f"The file extension (.{declared}) does not match the file content "
                f"(.{kind}).",
                "mime_mismatch",
            )
    return declared


def store_upload(file_id: str, filename: str, data: bytes) -> dict:
    """Persist an uploaded file and return its record."""
    name = safe_filename(filename)
    path = job_upload_dir(file_id) / name
    path.write_bytes(data)
    return {
        "id": file_id,
        "name": name,
        "size": len(data),
        "format": Path(name).suffix.lstrip(".").lower(),
        "sha256": sha256_of_bytes(data),
    }
