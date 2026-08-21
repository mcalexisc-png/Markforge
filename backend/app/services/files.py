"""Upload validation: extension, magic bytes, size limits, safe names."""

from __future__ import annotations

import codecs
import json
from pathlib import Path

from app.core.config import settings
from app.core.security import safe_filename, sha256_of_bytes
from app.services.storage import job_upload_dir
from converters import ALLOWED_EXTENSIONS

_RESERVED_STEMS = {"CON", "PRN", "AUX", "NUL"} | {
    f"COM{i}" for i in range(1, 10)
} | {f"LPT{i}" for i in range(1, 10)}

_SIGNS: list[tuple[str, bytes]] = [
    ("pdf", b"%PDF"),
    ("zip", b"PK\x03\x04"),
]

# Outlook .msg files are OLE2 compound documents.
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# Formats carried inside an OOXML-style zip container, told apart by their parts.
_OOXML_EXTENSIONS = frozenset({"docx", "pptx", "xlsx"})

# Formats with no reliable magic bytes. They are validated by confirming the
# content is text rather than by sniffing a signature, because pretending to
# sniff a signature that does not exist would only give false confidence.
_TEXT_EXTENSIONS = frozenset(
    {"csv", "tsv", "html", "htm", "txt", "md", "json", "xml", "ipynb"}
)

# Formats within _TEXT_EXTENSIONS that must additionally parse as JSON.
_JSON_EXTENSIONS = frozenset({"json", "ipynb"})

_BOMS = (
    codecs.BOM_UTF8,
    codecs.BOM_UTF32_LE,
    codecs.BOM_UTF32_BE,
    codecs.BOM_UTF16_LE,
    codecs.BOM_UTF16_BE,
)

# Bytes that appear freely in real text. Everything else in the C0 range counts
# towards the "this is binary" ratio below.
_TEXT_CONTROL_BYTES = frozenset(b"\t\n\r\f\v\b\x1b")


def _looks_binary(sample: bytes) -> bool:
    """Heuristic binary check, deliberately forgiving of legacy encodings.

    A strict UTF-8 requirement would reject perfectly convertible latin-1 CSVs,
    so this looks for the things that actually indicate a binary payload: a NUL
    byte, or a high proportion of control characters.
    """
    if not sample:
        return False
    if sample.startswith(_BOMS):
        return False
    if b"\x00" in sample:
        return True
    control = sum(
        1 for byte in sample if byte < 0x20 and byte not in _TEXT_CONTROL_BYTES
    )
    return control / len(sample) > 0.3


def _validate_text_upload(declared: str, data: bytes) -> None:
    """Validate a text-family upload."""
    if _looks_binary(data[:8192]):
        raise UploadValidationError(
            f"This file does not look like a readable .{declared} text file.",
            "not_a_document",
        )
    if declared in _JSON_EXTENSIONS:
        try:
            json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UploadValidationError(
                f"This file is not valid JSON, so it cannot be read as .{declared}.",
                "not_a_document",
            ) from exc


def _is_epub(data: bytes) -> bool:
    """True when a zip archive is really an EPUB package."""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "META-INF/container.xml" in names:
                return True
            if "mimetype" in names:
                return archive.read("mimetype").strip() == b"application/epub+zip"
    except (zipfile.BadZipFile, KeyError, OSError):
        return False
    return False


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


async def read_upload_limited(upload) -> bytes:
    """Read an UploadFile into memory, aborting once it exceeds the size cap.

    The cap is enforced *during* the read so a huge body can never be fully
    buffered by the server.
    """
    limit = settings.effective_max_file_size
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(1024 * 1024):
        total += len(chunk)
        if total > limit:
            raise UploadValidationError(
                f"This file exceeds the {limit // (1024 * 1024)} MB size limit.",
                "file_too_large",
            )
        chunks.append(chunk)
    return b"".join(chunks)


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

    stem = Path(filename).stem.upper().rstrip(" .")
    if stem in _RESERVED_STEMS:
        raise UploadValidationError(
            "This filename is reserved by the operating system and cannot be used.",
            "invalid_filename",
        )

    if size > settings.effective_max_file_size:
        mb = settings.effective_max_file_size // (1024 * 1024)
        raise UploadValidationError(
            f"This file exceeds the {mb} MB size limit.", "file_too_large"
        )
    declared = ext.lstrip(".")

    # Text formats carry no signature to check, so they take a separate path.
    if declared in _TEXT_EXTENSIONS:
        _validate_text_upload(declared, first_bytes)
        return declared

    if declared == "msg":
        if not first_bytes.startswith(_OLE2_MAGIC):
            raise UploadValidationError(
                "This file does not look like an Outlook .msg message.",
                "not_a_document",
            )
        return declared

    if declared == "xls":
        if not first_bytes.startswith(_OLE2_MAGIC):
            raise UploadValidationError(
                "This file does not look like an Excel .xls spreadsheet.",
                "not_a_document",
            )
        return declared

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
        return declared

    if magic != "zip":
        raise UploadValidationError(
            f"This file does not look like a .{declared} archive.",
            "not_an_archive",
        )

    if declared == "epub":
        if not _is_epub(first_bytes):
            raise UploadValidationError(
                "The file extension (.epub) does not match the file content.",
                "mime_mismatch",
            )
        return declared

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
