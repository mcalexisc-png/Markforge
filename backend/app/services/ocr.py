"""Local OCR support for scanned PDFs.

Uses Tesseract through pytesseract (or OCRmyPDF as an alternative engine)
running entirely on the host. When no OCR engine is installed the service
reports the limitation through warnings instead of failing the job.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from converters.base import ConversionContext

logger = logging.getLogger("markforge.ocr")

_tesseract_available: bool | None = None
_ocrmypdf_available: bool | None = None


def tesseract_available() -> bool:
    global _tesseract_available
    if _tesseract_available is None:
        _tesseract_available = bool(shutil.which("tesseract"))
    return _tesseract_available


def ocrmypdf_available() -> bool:
    global _ocrmypdf_available
    if _ocrmypdf_available is None:
        _ocrmypdf_available = bool(shutil.which("ocrmypdf"))
    return _ocrmypdf_available


def engine_available() -> str | None:
    """Name of the preferred OCR engine, or None when nothing is installed."""
    try:
        import pytesseract  # noqa: F401

        if tesseract_available():
            return "tesseract"
    except ImportError:
        pass
    if ocrmypdf_available():
        return "ocrmypdf"
    return None


def ocr_pdf_pages(doc, pages: set[int], context: ConversionContext) -> bool:
    """OCR the given page numbers in-place, filling ``context.ocr_texts``.

    Returns True when at least one page produced usable text.
    """
    if not pages:
        return False
    engine = engine_available()
    if not engine:
        logger.warning("OCR requested but no OCR engine is installed (job=%s)", context.job_id)
        return False

    succeeded = False
    ordered = sorted(pages)
    for index, page_number in enumerate(ordered, start=1):
        context.progress(
            "ocr",
            index,
            len(ordered),
            f"OCR page {page_number + 1} of {doc.page_count}",
        )
        try:
            page = doc[page_number]
            text = _ocr_page(page, engine)
        except Exception as exc:  # OCR engines fail in many unhelpful ways
            logger.warning("OCR failed on page %s: %s", page_number + 1, exc)
            continue
        if text and text.strip():
            context.ocr_texts[page_number] = text.strip()
            succeeded = True
    return succeeded


def _ocr_page(page, engine: str) -> str:
    if engine == "tesseract":
        import pytesseract

        pixmap = page.get_pixmap(dpi=300, colorspace="rgb", alpha=False)
        from PIL import Image

        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        return pytesseract.image_to_string(image)

    if engine == "ocrmypdf":
        import ocrmypdf
        import pymupdf

        return _ocr_page_ocrmypdf(page, ocrmypdf, pymupdf)
    return ""


def _ocr_page_ocrmypdf(page, ocrmypdf, pymupdf) -> str:
    """Fallback: OCR a single page by writing a temp PDF and running OCRmyPDF."""
    import tempfile

    source_doc = page.parent
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "page.pdf"
        target = Path(tmp) / "page-ocr.pdf"
        single = pymupdf.open()
        single.insert_pdf(source_doc, from_page=page.number, to_page=page.number)
        single.save(source)
        single.close()
        ocrmypdf.ocr(source, target, force_ocr=True, deskew=False, output_type="pdf")
        result = pymupdf.open(target)
        try:
            return "\n".join(p.get_text() for p in result)
        finally:
            result.close()

