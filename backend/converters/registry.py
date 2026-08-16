"""Converter registry: format detection and instantiation."""

from __future__ import annotations

from pathlib import Path

from converters.base import BaseConverter, ConversionContext, UnsupportedFormatError
from converters.docx import DocxConverter
from converters.pdf import PdfConverter
from converters.pptx import PptxConverter
from converters.xlsx import XlsxConverter

SUPPORTED_FORMATS: dict[str, type[BaseConverter]] = {
    "pdf": PdfConverter,
    "docx": DocxConverter,
    "pptx": PptxConverter,
    "xlsx": XlsxConverter,
}

# Formats planned for future releases (architecture is ready for them).
PLANNED_FORMATS = ["txt", "csv", "html", "odt", "ods", "odp", "rtf", "epub"]

ALLOWED_EXTENSIONS = tuple(
    sorted({ext for converter in SUPPORTED_FORMATS.values() for ext in converter.extensions})
)


def detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    for fmt, converter in SUPPORTED_FORMATS.items():
        if ext in converter.extensions:
            return fmt
    raise UnsupportedFormatError(
        f"Files with the .{ext.lstrip('.')} extension are not supported yet.",
        code="unsupported_format",
        detail=f"Supported formats: {', '.join(SUPPORTED_FORMATS)}.",
    )


def create_converter(context: ConversionContext) -> BaseConverter:
    fmt = detect_format(context.source_path.name)
    return SUPPORTED_FORMATS[fmt](context)
