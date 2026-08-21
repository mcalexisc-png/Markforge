"""Embedded image extraction for the MarkItDown pipeline.

MarkItDown produces text only, so figures are pulled out of the source file
here and written into the job's ``assets/`` directory through
:meth:`ConversionContext.save_image`, which deduplicates by content hash. The
resulting ``![alt](assets/name.ext)`` references are anchored back into the
flat Markdown using the ``<!-- Page N -->`` and ``<!-- Slide number: N -->``
markers the custom converters already emit.

Real documents are full of logos, rules and spacer pixels, so everything is
filtered through :func:`is_decorative` before it is written. Getting that
filter wrong is the difference between useful figures and unreadable noise.
"""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

logger = logging.getLogger("markforge.images")

# An image must clear all of these to be considered content rather than
# decoration. Tuned to keep diagrams, charts and photographs while dropping
# bullets, spacers, rules and letterhead marks.
MIN_DIMENSION = 64          # px on the shorter axis
MIN_AREA = 100 * 100        # px
MAX_ASPECT_RATIO = 20.0     # rules and dividers are extremely elongated
MIN_BYTES = 1024            # a solid-colour placeholder compresses to nothing

# MarkItDown emits this stub wherever a DOCX carries an inline image (it
# writes a truncated "base64..." rather than the real payload). It is a
# stable positional anchor, so DOCX figures can be placed exactly.
DATA_URI_STUB_RE = re.compile(r"!\[([^\]]*)\]\(data:[^)]*\)")

PAGE_MARKER_RE = re.compile(r"<!-- Page (\d+) -->")
SLIDE_MARKER_RE = re.compile(r"<!-- Slide number: (\d+) -->")

_MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff",
}


def is_decorative(width: int, height: int, size_bytes: int) -> bool:
    """True when an image is too small, thin or trivial to be a real figure."""
    if width <= 0 or height <= 0:
        return True
    if size_bytes < MIN_BYTES:
        return True
    if min(width, height) < MIN_DIMENSION:
        return True
    if width * height < MIN_AREA:
        return True
    # Rules and dividers are extremely elongated.
    return max(width, height) / min(width, height) > MAX_ASPECT_RATIO


def extract_pdf_images(source: Path, context) -> dict[int, list[tuple[str, str]]]:
    """Extract page images from a PDF.

    Returns ``{page_number: [(relative_path, alt_text), ...]}`` using 1-based
    page numbers so the result lines up with the ``<!-- Page N -->`` markers.
    """
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - pymupdf is a core dependency
        return {}

    try:
        doc = pymupdf.open(source)
    except Exception:
        return {}

    by_page: dict[int, list[tuple[str, str]]] = {}
    try:
        for page_index, page in enumerate(doc, start=1):
            try:
                images = page.get_images(full=True)
            except Exception:
                continue
            kept = 0
            for entry in images:
                xref = entry[0]
                try:
                    info = doc.extract_image(xref)
                except Exception:
                    continue
                data = info.get("image") or b""
                if is_decorative(
                    int(info.get("width", 0)), int(info.get("height", 0)), len(data)
                ):
                    continue
                rel = context.save_image(data, info.get("ext", "png"))
                if rel:
                    # Number the figures that survive, not the raw image slots:
                    # a filtered logo must not push the first real figure to 2.
                    kept += 1
                    alt = f"Figure {kept} on page {page_index}"
                    by_page.setdefault(page_index, []).append((rel, alt))
    finally:
        doc.close()
    return by_page


def _natural_key(name: str) -> tuple:
    """Sort ``image2.png`` before ``image10.png``.

    OOXML numbers its media sequentially in document order, so natural sorting
    is what recovers that order -- lexicographic sorting would scramble it once
    a document has ten or more images.
    """
    return tuple(
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", name)
    )


def _iter_zip_media(source: Path, prefix: str):
    """Yield ``(data, ext)`` for each media part, in document order."""
    try:
        archive = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError):
        return
    with archive:
        names = [
            n
            for n in archive.namelist()
            if n.startswith(prefix) and Path(n).suffix.lower() in _MEDIA_EXTENSIONS
        ]
        for name in sorted(names, key=_natural_key):
            try:
                yield archive.read(name), Path(name).suffix.lower().lstrip(".")
            except (KeyError, OSError):
                continue


def extract_zip_media(source: Path, context, prefix: str) -> list[tuple[str, str]]:
    """Extract embedded media from an OOXML-style package.

    ``prefix`` is the archive folder to read (``word/media/`` for DOCX,
    ``xl/media/`` for XLSX).
    """
    results: list[tuple[str, str]] = []
    for order, (data, ext) in enumerate(_iter_zip_media(source, prefix), start=1):
        width, height = _image_size(data)
        if is_decorative(width, height, len(data)):
            continue
        rel = context.save_image(data, ext)
        if rel:
            results.append((rel, f"Figure {order}"))
    return results


def replace_data_uri_stubs(
    markdown: str, source: Path, context, prefix: str
) -> tuple[str, int]:
    """Swap MarkItDown's inline image stubs for real extracted assets.

    The Nth stub pairs with the Nth media part, which keeps every figure in its
    original position. A stub whose image is decorative is removed outright
    rather than left behind as an empty reference, and the pairing stays in step
    because both sequences are walked together.
    """
    stubs = list(DATA_URI_STUB_RE.finditer(markdown))
    if not stubs:
        return markdown, 0

    media = list(_iter_zip_media(source, prefix))
    parts: list[str] = []
    last = 0
    saved = 0
    for index, match in enumerate(stubs):
        parts.append(markdown[last : match.start()])
        replacement = ""
        if index < len(media):
            data, ext = media[index]
            width, height = _image_size(data)
            if not is_decorative(width, height, len(data)):
                rel = context.save_image(data, ext)
                if rel:
                    alt = match.group(1) or f"Figure {saved + 1}"
                    replacement = f"![{alt}]({rel})"
                    saved += 1
        parts.append(replacement)
        last = match.end()
    parts.append(markdown[last:])
    return "".join(parts), saved


def _image_size(data: bytes) -> tuple[int, int]:
    """Best-effort pixel dimensions, so the decorative filter can be applied."""
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            return image.width, image.height
    except Exception:
        # Unknown dimensions: fall back to size alone rather than dropping it.
        return MIN_DIMENSION, MIN_DIMENSION


def _render(items: list[tuple[str, str]]) -> str:
    return "".join(f"\n\n![{alt}]({rel})" for rel, alt in items)


def insert_at_markers(
    markdown: str,
    by_number: dict[int, list[tuple[str, str]]],
    marker_re: re.Pattern[str],
) -> str:
    """Insert image references directly after their page/slide marker."""
    if not by_number or not marker_re.search(markdown):
        return markdown
    parts: list[str] = []
    last = 0
    for match in marker_re.finditer(markdown):
        parts.append(markdown[last : match.end()])
        items = by_number.get(int(match.group(1)))
        if items:
            parts.append(_render(items))
        last = match.end()
    parts.append(markdown[last:])
    return "".join(parts)


def append_figures_section(markdown: str, items: list[tuple[str, str]]) -> str:
    """Append figures that carry no positional anchor.

    DOCX and XLSX give no reliable way to locate an image within MarkItDown's
    flat output, so rather than guess a position they are collected at the end
    under a heading. Being obviously grouped is better than being silently
    misplaced mid-sentence.
    """
    if not items:
        return markdown
    body = _render(items).lstrip("\n")
    return f"{markdown.rstrip()}\n\n## Figures\n\n{body}\n"


def flatten(by_number: dict[int, list[tuple[str, str]]]) -> list[tuple[str, str]]:
    return [item for _, items in sorted(by_number.items()) for item in items]
