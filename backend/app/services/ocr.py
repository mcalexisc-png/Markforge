"""Local OCR support for scanned PDFs.

Uses Tesseract through pytesseract (or OCRmyPDF as an alternative engine)
running entirely on the host. When no OCR engine is installed the service
reports the limitation through warnings instead of failing the job.
"""

from __future__ import annotations

import logging
import shutil

logger = logging.getLogger("markforge.ocr")

_tesseract_available: bool | None = None


def tesseract_available() -> bool:
    global _tesseract_available
    if _tesseract_available is None:
        _tesseract_available = bool(shutil.which("tesseract"))
    return _tesseract_available
