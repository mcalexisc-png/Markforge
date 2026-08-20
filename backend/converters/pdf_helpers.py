"""Shared PDF pre-pass helpers for both conversion engines.

Both the built-in converter and the MarkItDown adapter benefit from two
pre-passes over the source file:

* duplicate-slide removal: PowerPoint animation builds are exported to PDF
  as consecutive pages with identical text; the duplicates carry no new
  information;
* textless-page analysis: a mostly-text PDF whose few image-only pages are
  decorative covers should not be OCR'd (OCR noise); a mostly-image PDF is
  a real scan and must be OCR'd page by page.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

_MIN_TEXT_CHARS = 20  # matches the built-in PDF converter's scan threshold


def textless_pages(path: Path) -> tuple[set[int], int] | None:
    """Return (set of 1-based page numbers without text, total pages)."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - pymupdf is a core dependency
        return None
    try:
        doc = pymupdf.open(path)
    except Exception:
        return None
    try:
        total = doc.page_count
        textless = {
            index
            for index, page in enumerate(doc, start=1)
            if len(re.sub(r"\s+", "", page.get_text())) < _MIN_TEXT_CHARS
        }
        return textless, total
    finally:
        doc.close()


def dedupe_duplicate_pages(path: Path) -> tuple[Path | None, int]:
    """Remove consecutive pages with identical text into a temp copy.

    Returns (path_to_filtered_copy, removed_count). A textless page is
    never treated as a duplicate of another textless page.
    """
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - pymupdf is a core dependency
        return None, 0
    try:
        doc = pymupdf.open(path)
    except Exception:
        return None, 0
    try:
        signatures: list[str] = []
        to_delete: list[int] = []
        prev_index: int | None = None
        for index, page in enumerate(doc):
            sig = re.sub(r"\s+", "", page.get_text())
            if not sig:
                prev_index = None
                continue
            if prev_index is not None and sig == signatures[prev_index]:
                to_delete.append(index)
            else:
                signatures.append(sig)
                prev_index = len(signatures) - 1
        if not to_delete:
            return None, 0
        tmp = Path(tempfile.mkdtemp(prefix="markforge-dedupe-"))
        target = tmp / "dedupe.pdf"
        keep = [i for i in range(doc.page_count) if i not in to_delete]
        doc.select(keep)
        doc.save(target, garbage=3, deflate=True)
        return target, len(to_delete)
    finally:
        doc.close()


def cleanup_temp_copy(copy: Path) -> None:
    """Remove the temp directory holding a dedupe/OCR copy."""
    if copy is not None:
        shutil.rmtree(copy.parent, ignore_errors=True)