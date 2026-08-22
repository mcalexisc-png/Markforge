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

import pymupdf
from markitdown._base_converter import DocumentConverterResult
from markitdown.converters import PdfConverter

_BODY_RATIO = 1.2  # lines >= 1.2x the page's median font size become headings
_MAX_TITLE_CHARS = 100
_BOLD_FLAG = 1 << 4  # PyMuPDF span flag for bold text
_MARKER_LINE_RE = re.compile(r"^(?:[✔✓☑☒●•◦▪‣–—\-]|\d+[.)])$")

# Same glyph set as _MARKER_LINE_RE, but matched as a *prefix* (glyph +
# optional/required whitespace) rather than a whole-line match, so an inline
# bullet like "●Pwersahang paghalik..." (PDF export often omits the space
# between the glyph and its text) is recognized too, not just a bullet that
# arrived on its own line.
#
# The bullet-icon and checkmark glyphs are unambiguous -- nobody writes "●" or
# "✔" as ordinary punctuation -- so any amount of following whitespace (even
# none) counts. A plain "-"/"–"/"—" and a digit followed by "." are genuinely
# ambiguous with a hyphen, a minus sign, or a decimal ("3.5 million"), so
# those two require at least one space after the punctuation before they are
# treated as a list marker.
#
# The optional (?:\*\*)? on both sides handles a glyph that was individually
# bold-styled in the source PDF (_wrap_bold wraps just that one span), e.g.
# "**●** Log in..." -- observed in real converted output.
_NUMBER_PREFIX_RE = re.compile(r"^(?:\*\*)?(\d+)[.)](?:\*\*)?\s+")
_CHECK_PREFIX_RE = re.compile(r"^(?:\*\*)?[✔✓☑☒](?:\*\*)?\s*")
_BULLET_GLYPH_PREFIX_RE = re.compile(r"^(?:\*\*)?[●•◦▪‣](?:\*\*)?\s*")
_DASH_PREFIX_RE = re.compile(r"^(?:\*\*)?[\-–—](?:\*\*)?\s+")

# PyMuPDF preserves typographic ligatures (ﬀ, ﬁ, ﬂ, ﬃ, ...) as single glyphs
# by default, so "Effects" extracts as "Eﬀects" and "Office" as "Oﬃce" --
# copy-pasted or searched text then silently fails to match the plain-ASCII
# word a reader typed. Decomposing them back to their component letters is
# what a person reading the source PDF actually sees.
_TEXT_DICT_FLAGS = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_LIGATURES


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


def _normalize_bullet_prefix(text: str) -> str:
    """Rewrite a leading bullet/checkmark/number glyph as real Markdown list syntax.

    PyMuPDF hands back whatever glyph the PDF printed for a bullet (``●``,
    ``✔``, ...) as a literal character; a Markdown renderer just shows that
    character, it does not render a list. Rewriting it to ``- ``, ``- ✔ `` or
    ``N. `` is what makes it render as an actual list item. If ``text`` does
    not start with a recognized glyph, it is returned unchanged.
    """
    if m := _NUMBER_PREFIX_RE.match(text):
        return f"{m.group(1)}. {text[m.end():]}"
    if _CHECK_PREFIX_RE.match(text):
        return "- ✔ " + _CHECK_PREFIX_RE.sub("", text, count=1)
    if _BULLET_GLYPH_PREFIX_RE.match(text):
        return "- " + _BULLET_GLYPH_PREFIX_RE.sub("", text, count=1)
    if _DASH_PREFIX_RE.match(text):
        return "- " + _DASH_PREFIX_RE.sub("", text, count=1)
    return text


def _extract_page(page) -> str:
    """Extract one page as Markdown lines in document (column) order."""
    data = page.get_text("dict", flags=_TEXT_DICT_FLAGS)
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
    # Tracks the (font size, raw text) of the most recently *appended plain or
    # list line*, so the next line can decide whether it continues that line
    # or starts a new one. Reset to None after a heading or a lone marker,
    # which nothing may be glued onto or glued out of.
    pending: tuple[float, str] | None = None
    index = 0
    while index < len(lines):
        size, text = lines[index]
        if _MARKER_LINE_RE.match(text.replace("**", "")):
            # Standalone markers (bullets, numbers, checkmarks) merge with the
            # next content line so lists read as "- text" / "1. text" instead
            # of a bare glyph on its own line.
            markers = [text]
            next_index = index + 1
            while next_index < len(lines) and _MARKER_LINE_RE.match(
                lines[next_index][1].replace("**", "")
            ):
                markers.append(lines[next_index][1])
                next_index += 1
            # A run of several standalone marker lines in a row (observed:
            # four consecutive "•" lines before a section label) is a
            # repeated decorative divider, not N distinct list items -- only
            # the first is kept, so the divider becomes one list marker
            # instead of leaving the extras stuck mid-line as literal glyphs.
            marker = markers[0]
            if next_index < len(lines):
                next_size, next_text = lines[next_index]
                if len(markers) == 1 and is_heading(next_size, next_text):
                    # A lone marker directly before a heading is decorative
                    # (e.g. a divider glyph); keep it on its own line rather
                    # than gluing it onto an unrelated title.
                    out.append(_normalize_bullet_prefix(marker))
                    pending = None
                    index += 1
                    continue
                combined = _normalize_bullet_prefix(marker + " " + next_text)
                out.append(combined)
                # The list item's own text may still wrap onto further plain
                # lines below (see the reflow branch), so it stays open.
                pending = (next_size, combined)
                index = next_index + 1
            else:
                out.append(_normalize_bullet_prefix(marker))
                pending = None
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
            pending = None
            continue

        normalized = _normalize_bullet_prefix(text)
        # A line only continues whatever precedes it when: it's the same font
        # size as that line, that line didn't already end its sentence, and
        # this line reads as a continuation rather than a new one starting.
        # Requiring a lowercase first character is what tells "tumataas"
        # (continues "Dito") apart from "Paggamit ng isang tao..." (a new
        # clause) -- and, as a side effect, a normalized "- " or "N. " list
        # prefix is never lowercase, so a fresh list item is never glued onto
        # whatever came before it.
        if (
            pending is not None
            and size == pending[0]
            and not pending[1].rstrip().endswith((".", "!", "?", ":"))
            and normalized[:1].islower()
        ):
            merged = out[-1] + " " + normalized
            out[-1] = merged
            pending = (size, merged)
        else:
            out.append(normalized)
            pending = (size, normalized)
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