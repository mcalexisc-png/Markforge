"""Column-aware PDF converter for the MarkItDown engine.

MarkItDown's built-in PDF converter reads pages with pdfplumber, which
y-sorts extracted lines and interleaves multi-column layouts (e.g. slide
decks with side-by-side columns). This converter instead extracts each
page with PyMuPDF in document (column) order, promotes large-font lines to
Markdown headings, merges standalone checkmark glyphs into the following
line, and emits a ``<!-- Page N -->`` marker per page (stripped by the
settings filters in Clean mode, kept in Fidelity mode).

Table/form detection of the built-in converter is intentionally dropped:
the app's own settings filters already turn tables into plain text when
``convert_tables`` is off, and structured spreadsheets should use XLSX.
"""

from __future__ import annotations

import io
import re
import statistics

from markitdown._base_converter import DocumentConverterResult
from markitdown.converters import PdfConverter

_BODY_RATIO = 1.2  # lines >= 1.2x the page's median font size become headings
_MAX_TITLE_CHARS = 100
_BOLD_FLAG = 1 << 4  # PyMuPDF span flag for bold text
_MARKER_LINE_RE = re.compile(r"^(?:[✔✓☑☒●•◦▪‣–—\-]|\d+[.)])$")


def _is_bold(span: dict) -> bool:
    if span.get("flags", 0) & _BOLD_FLAG:
        return True
    return "Bold" in span.get("font", "") or "bold" in span.get("font", "")


def _wrap_bold(span_text: str) -> str:
    """Wrap a bold span, keeping surrounding whitespace outside the markers."""
    stripped = span_text.strip()
    if not stripped:
        return span_text
    leading = span_text[: len(span_text) - len(span_text.lstrip())]
    trailing = span_text[len(span_text.rstrip()) :]
    return leading + f"**{stripped}**" + trailing


def _extract_page(page) -> str:
    """Extract one page as Markdown lines in document (column) order."""
    data = page.get_text("dict")
    lines: list[tuple[float, str]] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text")]
            if not spans:
                continue
            parts: list[str] = []
            for span in spans:
                text = span["text"]
                if text.strip() and _is_bold(span):
                    text = _wrap_bold(text)
                parts.append(text)
            text = "".join(parts).strip()
            if not text:
                continue
            size = max(s.get("size", 0) for s in spans)
            lines.append((size, text))
    if not lines:
        return ""

    if len(lines) <= 4 and len({size for size, _ in lines}) == 1:
        # Title-only page: a handful of same-sized lines is a title slide.
        text = " ".join(text for _, text in lines).replace("**", "")
        return "## " + re.sub(r"\s+", " ", text).strip()

    body_size = statistics.median(size for size, _ in lines)
    threshold = body_size * _BODY_RATIO

    def is_heading(size: float, text: str) -> bool:
        return (
            size >= threshold
            and len(text) <= _MAX_TITLE_CHARS
            and not text.startswith("#")
        )

    out: list[str] = []
    index = 0
    while index < len(lines):
        size, text = lines[index]
        if _MARKER_LINE_RE.match(text.replace("**", "")):
            # Standalone markers (bullets, numbers, checkmarks) merge with the
            # next content line so lists read as "● text" / "1. text".
            markers = [text]
            next_index = index + 1
            while next_index < len(lines) and _MARKER_LINE_RE.match(
                lines[next_index][1].replace("**", "")
            ):
                markers.append(lines[next_index][1])
                next_index += 1
            if next_index < len(lines):
                next_size, next_text = lines[next_index]
                if len(markers) == 1 and is_heading(next_size, next_text):
                    out.append(" ".join(markers))
                    index += 1
                    continue
                out.append(" ".join(markers) + " " + next_text)
                index = next_index + 1
            else:
                out.append(" ".join(markers))
                index = next_index
            continue
        if is_heading(size, text):
            heading_parts = [text]
            index += 1
            while index < len(lines):
                next_size, next_text = lines[index]
                if not is_heading(next_size, next_text):
                    break
                heading_parts.append(next_text)
                index += 1
            joined = " ".join(part.replace("**", "") for part in heading_parts)
            joined = re.sub(r"\s+", " ", joined).strip()
            out.append(f"## {joined}")
            continue
        out.append(text)
        index += 1
    return "\n".join(out)


class ColumnAwarePdfConverter(PdfConverter):
    """PyMuPDF-based PDF converter with column order and heading promotion."""

    def convert(self, file_stream, stream_info, **kwargs):
        pdf_bytes = io.BytesIO(file_stream.read())
        try:
            import pymupdf
        except ImportError:
            pdf_bytes.seek(0)
            return super().convert(pdf_bytes, stream_info, **kwargs)
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        except Exception:
            pdf_bytes.seek(0)
            return super().convert(pdf_bytes, stream_info, **kwargs)
        try:
            chunks: list[str] = []
            for page_index, page in enumerate(doc, start=1):
                text = _extract_page(page)
                if text:
                    chunks.append(f"<!-- Page {page_index} -->\n{text}")
                else:
                    chunks.append(f"<!-- Page {page_index} -->")
            markdown = "\n\n".join(chunks).strip()
            if not markdown:
                pdf_bytes.seek(0)
                return super().convert(pdf_bytes, stream_info, **kwargs)
            return DocumentConverterResult(markdown=markdown)
        finally:
            doc.close()