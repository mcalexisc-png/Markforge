"""MarkItDown engine adapter.

Microsoft's ``markitdown`` library converts files directly to Markdown text
without the Common Document Model. This adapter wraps it so the job pipeline
keeps the same contract: it returns a :class:`Document` carrying heuristic
stats and warnings, and stores the produced Markdown on the context.

Scanned PDFs are OCR'd first (Tesseract via OCRmyPDF on a temp copy) so the
local OCR capability keeps working; the converted file is never modified.
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
from pathlib import Path

from app.services.ocr import tesseract_available
from converters.base import ConversionContext, ConversionError
from converters.markitdown_pdf import ColumnAwarePdfConverter
from converters.markitdown_pptx import HeadingPptxConverter
from converters.pdf_helpers import dedupe_duplicate_pages, textless_pages
from document_model.document import ConversionWarning, Document, DocumentStats
from document_model.metadata import normalize_metadata
from markdown.settings_filters import apply_settings_filters

logger = logging.getLogger("markforge.markitdown")

_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
_LIST_RE = re.compile(r"^\s*[-*+]\s+\S|^[●•]\s*\S")
_TABLE_LINE_RE = re.compile(r"^\s*\|")
_LINK_RE = re.compile(r"\]\(")
_CODE_FENCE_RE = re.compile(r"^```")
_PAGE_MARKER_RE = re.compile(r"<!-- Page (\d+) -->")
_SLIDE_MARKER_RE = re.compile(r"<!-- Slide number: (\d+) -->")


def _detect_scanned_pdf(path: Path) -> bool:
    """True when at least one page has almost no extractable text."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - pymupdf is a core dependency
        return False
    try:
        doc = pymupdf.open(path)
    except Exception:
        return False
    try:
        return any(
            len(re.sub(r"\s+", "", page.get_text())) < 20
            for page in doc
        )
    finally:
        doc.close()


def _insert_image_placeholders(markdown: str, textless: set[int], label: str) -> str:
    """Mark pages that carry no text with a placeholder instead of OCR noise."""
    if not _PAGE_MARKER_RE.search(markdown):
        return markdown
    parts: list[str] = []
    last = 0
    for match in _PAGE_MARKER_RE.finditer(markdown):
        parts.append(markdown[last : match.start()])
        parts.append(match.group(0))
        if int(match.group(1)) in textless:
            parts.append(f"\n\n[{label}]")
        last = match.end()
    parts.append(markdown[last:])
    return "".join(parts)


def _ocrmypdf_importable() -> bool:
    try:
        import ocrmypdf  # noqa: F401
    except ImportError:
        return False
    return True


def _ocr_engine_available() -> bool:
    """True when both the Tesseract binary and the ocrmypdf package are present."""
    return tesseract_available() and _ocrmypdf_importable()


def _ocr_pdf_copy(source: Path, context: ConversionContext, *, force_ocr: bool = False) -> Path | None:
    """OCR a scanned PDF into a temp copy and return its path (or None)."""
    tmp = Path(tempfile.mkdtemp(prefix="markforge-ocr-"))
    target = tmp / "ocr.pdf"
    try:
        import ocrmypdf
    except ImportError:
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    context.progress("ocr", 0, 1, "OCR pages")
    try:
        ocrmypdf.ocr(
            source,
            target,
            force_ocr=force_ocr,
            skip_text=not force_ocr,
            deskew=False,
            output_type="pdf",
        )
        return target
    except Exception as exc:
        logger.warning("OCR pre-pass failed: %s", exc)
        shutil.rmtree(tmp, ignore_errors=True)
        return None


def _heuristic_stats(markdown: str, fmt: str) -> DocumentStats:
    """Derive approximate stats from the produced Markdown text."""
    stats = DocumentStats()
    headings = 0
    lists = 0
    tables = 0
    fences = 0
    in_table = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _HEADING_RE.match(stripped):
            headings += 1
        elif _TABLE_LINE_RE.match(stripped):
            if not in_table:
                tables += 1
                in_table = True
        elif _LIST_RE.match(stripped):
            lists += 1
            in_table = False
        else:
            in_table = False
        if _CODE_FENCE_RE.match(stripped):
            fences += 1
    stats.headings = headings
    stats.lists = lists
    stats.tables = tables
    stats.code_blocks = max(fences // 2, 0)
    stats.links = len(_LINK_RE.findall(markdown))
    if fmt == "pdf":
        stats.pages = len(_PAGE_MARKER_RE.findall(markdown))
    elif fmt == "pptx":
        stats.slides = len(_SLIDE_MARKER_RE.findall(markdown))
    elif fmt == "xlsx":
        stats.sheets = headings  # every xlsx sheet becomes one `## name` heading
    paragraphs = [b for b in re.split(r"\n\s*\n", markdown) if b.strip()]
    stats.paragraphs = len(paragraphs)
    return stats


def convert_with_markitdown(context: ConversionContext) -> Document:
    """Convert the context's source file with MarkItDown.

    Returns a minimal :class:`Document` (no blocks) and stores the Markdown
    text on ``context.markdown_output`` for the job pipeline to write out.
    """
    source = Path(context.source_path)
    fmt = source.suffix.lower().lstrip(".") or "file"
    path_for_conversion: Path = source
    dedupe_copy: Path | None = None
    ocr_pages = 0
    warnings: list[ConversionWarning] = []
    textless_set: set[int] = set()
    deck_mode = False

    if fmt == "pdf":
        dedupe_copy, removed = dedupe_duplicate_pages(source)
        if dedupe_copy is not None:
            path_for_conversion = dedupe_copy
            if removed:
                warnings.append(
                    ConversionWarning(
                        code="duplicate_pages_removed",
                        message=(
                            f"Removed {removed} duplicate slide page(s) with "
                            "identical content (animation builds)."
                        ),
                        severity="info",
                    )
                )
        analysis = textless_pages(path_for_conversion)
        if analysis is not None:
            textless_set, total = analysis
            deck_mode = bool(textless_set) and (len(textless_set) / total) < 0.5

    if fmt == "pdf" and context.settings.ocr_mode != "never":
        force_ocr = context.settings.ocr_mode == "always"
        needs_ocr = False
        if force_ocr:
            needs_ocr = True
        elif deck_mode:
            needs_ocr = False  # mostly-text document: image pages are decorative
        elif textless_set:
            needs_ocr = True  # mostly image pages: real scanned document
        else:
            needs_ocr = _detect_scanned_pdf(path_for_conversion)
        if needs_ocr:
            if _ocr_engine_available():
                ocr_copy = _ocr_pdf_copy(path_for_conversion, context, force_ocr=force_ocr)
                if ocr_copy is not None:
                    path_for_conversion = ocr_copy
                    context.ocr_used = True
                    try:
                        import pymupdf
                        with pymupdf.open(path_for_conversion) as doc:
                            ocr_pages = doc.page_count
                    except Exception:
                        pass
                    context.progress("ocr", 1, 1, "OCR complete")
                    warnings.append(
                        ConversionWarning(
                            code="ocr_used",
                            message=f"{ocr_pages} scanned page(s) processed with local OCR",
                            severity="info",
                        )
                    )
            else:
                warnings.append(
                    ConversionWarning(
                        code="ocr_unavailable",
                        message="Scanned page(s) detected but OCR is not available on this system",
                        severity="warning",
                    )
                )
        elif deck_mode:
            warnings.append(
                ConversionWarning(
                    code="decorative_pages_skipped",
                    message=(
                        f"{len(textless_set)} page(s) had no extractable text and "
                        "were treated as decorative images (not OCR'd)."
                    ),
                    severity="info",
                )
            )

    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        md.register_converter(ColumnAwarePdfConverter())
        md.register_converter(HeadingPptxConverter())
        result = md.convert_local(str(path_for_conversion))
        text = result.text_content or ""
    except Exception as exc:
        raise ConversionError(
            "The file could not be converted to Markdown.",
            code="conversion_failed",
            detail=str(exc)[:500],
        ) from exc
    finally:
        if path_for_conversion is not source:
            shutil.rmtree(path_for_conversion.parent, ignore_errors=True)
        if dedupe_copy is not None and path_for_conversion is not dedupe_copy:
            shutil.rmtree(dedupe_copy.parent, ignore_errors=True)

    if fmt == "pdf" and textless_set and not context.ocr_used:
        label = "Slide image — no text" if deck_mode else "Image page — no text"
        text = _insert_image_placeholders(text, textless_set, label)

    context.markdown_output = apply_settings_filters(text, context.settings)

    doc = Document(
        format=fmt,
        filename=source.name,
        metadata=normalize_metadata({"title": source.stem}),
        stats=_heuristic_stats(context.markdown_output, fmt),
        warnings=warnings,
    )
    doc.stats.ocr_pages = ocr_pages
    return doc