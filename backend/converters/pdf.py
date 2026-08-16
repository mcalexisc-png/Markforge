"""PDF converter built on PyMuPDF.

Extracts text blocks per page, detects headings by font size, identifies
lists, tables and links, and pulls embedded images. Scanned pages are routed
through the OCR service when the OCR mode permits it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from converters.base import BaseConverter, ConversionContext, CorruptFileError
from document_model.blocks import (
    BulletListBlock,
    HeadingBlock,
    HorizontalRuleBlock,
    ImageBlock,
    LinkBlock,
    NumberedListBlock,
    PageBreakBlock,
    ParagraphBlock,
    TableBlock,
    TableCell,
    TableRow,
    TextRun,
)
from document_model.document import Document

_BULLET_CHARS = ("\u2022", "\u25aa", "\u25cf", "\u25e6", "-", "*")
_NUMBERED_RE = re.compile(r"^\(?\d{1,3}[.)]\s+")


class PdfConverter(BaseConverter):
    format = "pdf"
    extensions = (".pdf",)

    def __init__(self, context: ConversionContext):
        super().__init__(context)
        self._font_sizes: dict[float, int] = {}
        self._heading_sizes: set[float] = set()

    def convert(self) -> Document:
        path = Path(self.context.source_path)
        try:
            doc = pymupdf.open(path)
        except Exception as exc:  # pragma: no cover - PyMuPDF raises many types
            raise CorruptFileError("The PDF could not be opened or is corrupted.") from exc

        try:
            return self._convert_pages(doc)
        finally:
            doc.close()

    def _convert_pages(self, doc: pymupdf.Document) -> Document:
        total = doc.page_count
        metadata = dict(doc.metadata or {})
        blocks = []
        doc_model = self._build_document(metadata)
        stats = doc_model.stats

        # First pass: collect font sizes for heading detection.
        for page in doc:
            for b in page.get_text("dict", flags=0)["blocks"]:
                if b["type"] != 0:
                    continue
                for line in b["lines"]:
                    for span in line["spans"]:
                        size = round(span["size"], 1)
                        self._font_sizes[size] = self._font_sizes.get(size, 0) + len(span["text"])

        ordered = sorted(self._font_sizes.items(), key=lambda kv: kv[1], reverse=True)
        if ordered:
            median_size = ordered[len(ordered) // 2][0]
            self._heading_sizes = {s for s, _ in ordered if s > median_size * 1.25}
            if not self._heading_sizes:
                self._heading_sizes = {ordered[0][0]}

        # OCR detection pass when needed.
        ocr_pages = self._needs_ocr(doc) if self.context.settings.ocr_mode != "never" else set()
        if self.context.settings.ocr_mode == "always":
            ocr_pages = set(range(total))

        ocr_result = False
        if ocr_pages:
            from app.services.ocr import ocr_pdf_pages

            self.context.progress("ocr", 0, len(ocr_pages), "Detecting scanned pages")
            ocr_result = ocr_pdf_pages(doc, ocr_pages, self.context)

        if ocr_pages:
            self.context.ocr_used = ocr_result
            scanned_note = (
                f"{len(ocr_pages)} scanned page(s) processed with local OCR"
                if ocr_result
                else "Scanned page(s) detected but OCR is not available on this system"
            )
            doc_model.warnings.append(
                {
                    "code": "ocr_used" if ocr_result else "ocr_unavailable",
                    "message": scanned_note,
                    "severity": "info" if ocr_result else "warning",
                }
            )

        stats.ocr_pages = len(ocr_pages) if ocr_result else 0

        for page_index in range(total):
            page = doc[page_index]
            self.context.progress(
                "extract",
                page_index + 1,
                total,
                f"Extracting page {page_index + 1} of {total}",
            )
            blocks.append(PageBreakBlock(page_number=page_index + 1))
            self._convert_page(page, page_index, blocks, doc_model, ocr_pages)

        stats.pages = total
        doc_model.blocks = blocks
        doc_model.stats = stats
        return doc_model

    def _needs_ocr(self, doc: pymupdf.Document) -> set[int]:
        """Pages with little or no extractable text are treated as scans."""
        if self.context.settings.ocr_mode == "never":
            return set()
        needed: set[int] = set()
        for page_index, page in enumerate(doc):
            text = page.get_text().strip()
            chars = len(re.sub(r"\s+", "", text))
            if chars < 20:
                needed.add(page_index)
        return needed

    def _convert_page(
        self,
        page: pymupdf.Page,
        page_index: int,
        blocks: list,
        doc_model: Document,
        ocr_pages: set[int],
    ) -> None:
        stats = doc_model.stats

        images = page.get_images(full=True)
        if images:
            doc_handle = page.parent
            for img in images:
                try:
                    info = doc_handle.extract_image(img[0])
                except Exception:
                    continue
                data = info.get("image")
                if not data:
                    continue
                ext = (info.get("ext") or "png").lower()
                alt = f"Figure {img[0]}"
                rel = self.context.save_image(data, ext, alt=alt)
                if rel:
                    stats.images += 1
                    blocks.append(ImageBlock(path=rel, alt=alt))

        page_ocr_text: str | None = None
        if page_index in ocr_pages:
            page_ocr_text = self._get_ocr_text(page)

        raw_blocks = page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]
        text_blocks = [b for b in raw_blocks if b["type"] == 0]

        table_bboxes = self._convert_tables(page, blocks, doc_model)
        for b in self._reading_order(text_blocks, page):
            if any(self._bbox_inside(b["bbox"], tb) for tb in table_bboxes):
                continue
            self._convert_text_block(b, blocks, doc_model, stats)

        if page_ocr_text:
            for line in page_ocr_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if self._is_bullet(line):
                    stats.paragraphs += 1
                    blocks.append(BulletListBlock(items=[[TextRun(text=line.lstrip("•-* \t"))]]))
                else:
                    stats.paragraphs += 1
                    blocks.append(ParagraphBlock(content=[TextRun(text=line)]))

        links = page.get_links()
        if links and self.context.settings.preserve_links:
            for link in links:
                if link.get("kind") == pymupdf.LINK_URI and link.get("uri"):
                    stats.links += 1
                    blocks.append(
                        LinkBlock(
                            href=link["uri"],
                            content=[TextRun(text=link.get("uri", ""))],
                        )
                    )

    def _reading_order(self, blocks: list, page: pymupdf.Page) -> list:
        """Order text blocks for output.

        Pages with a clear two-column layout (a wide empty gutter, at least
        two blocks per side, vertically interleaved) are read left column
        first, then right column. Everything else falls back to reading
        order (top to bottom, left to right).
        """
        if len(blocks) < 4:
            return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

        width = page.rect.width
        min_gap = max(30.0, width * 0.08)
        centers = sorted((b["bbox"][0] + b["bbox"][2]) / 2 for b in blocks)

        best: tuple[float, float, float] | None = None
        for index in range(1, len(centers)):
            left_max = centers[index - 1]
            right_min = centers[index]
            gap = right_min - left_max
            if gap >= min_gap and index >= 2 and len(centers) - index >= 2 and (best is None or gap > best[0]):
                best = (gap, left_max, right_min)
        if best is None:
            return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

        _, left_max, right_min = best
        split = left_max + (right_min - left_max) / 2
        left = [b for b in blocks if (b["bbox"][0] + b["bbox"][2]) / 2 <= split]
        right = [b for b in blocks if (b["bbox"][0] + b["bbox"][2]) / 2 > split]
        if not left or not right:
            return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

        left_top, left_bottom = min(b["bbox"][1] for b in left), max(b["bbox"][1] for b in left)
        right_top, right_bottom = min(b["bbox"][1] for b in right), max(b["bbox"][1] for b in right)
        if left_bottom < right_top or right_bottom < left_top:
            return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

        left.sort(key=lambda b: b["bbox"][1])
        right.sort(key=lambda b: b["bbox"][1])
        return left + right

    def _get_ocr_text(self, page: pymupdf.Page) -> str | None:
        """OCR text provided by the OCR service (kept per page)."""
        return self.context.ocr_texts.get(page.number)

    @staticmethod
    def _bbox_inside(inner: tuple, outer: tuple, tolerance: float = 2.0) -> bool:
        """True when the inner bbox lies within the outer bbox (with slack)."""
        x0, y0, x1, y1 = inner
        ox0, oy0, ox1, oy1 = outer
        return x0 >= ox0 - tolerance and y0 >= oy0 - tolerance and x1 <= ox1 + tolerance and y1 <= oy1 + tolerance

    def _convert_tables(self, page: pymupdf.Page, blocks: list, doc_model: Document) -> list[tuple]:
        """Return the bboxes of tables actually emitted."""
        if not self.context.settings.convert_tables:
            return []
        try:
            found = page.find_tables()
        except Exception:
            return []
        if not found.tables:
            return []
        emitted: list[tuple] = []
        for table in found.tables:
            try:
                data = table.extract()
            except Exception:
                continue
            if not data or len(data) < 2:
                continue
            rows = []
            for row in data:
                cells = []
                for cell in row:
                    value = "" if cell is None else str(cell).strip()
                    cells.append(TableCell(content=[TextRun(text=value)]))
                rows.append(TableRow(cells=cells))
            if rows:
                blocks.append(TableBlock(rows=rows, has_header=True))
                doc_model.stats.tables += 1
                emitted.append(table.bbox)
        return emitted

    def _convert_text_block(
        self,
        block: dict,
        blocks: list,
        doc_model: Document,
        stats,
    ) -> None:
        lines = []
        size_rank: list[float] = []
        for line in block.get("lines", []):
            spans = [
                s for s in line.get("spans", []) if s.get("text", "").strip()
            ]
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans)
            size = max((s.get("size", 0) or 0) for s in spans)
            lines.append((text, size, spans))
            size_rank.append(size)

        if not lines:
            return

        text = lines[0][0].strip()

        if self._is_heading(text, lines):
            level = self._heading_level(max(s for _, s, _ in lines))
            runs = [self._span_to_run(s) for _, _, spans in lines for s in spans if s.get("text", "").strip()]
            blocks.append(HeadingBlock(level=level, content=runs))
            doc_model.stats.headings += 1
            return

        if text.startswith("---") or text == "***":
            blocks.append(HorizontalRuleBlock())
            return

        if self._is_bullet(text):
            items = []
            for _, _, spans in lines:
                items.append([self._span_to_run(s) for s in spans if s.get("text", "").strip()])
            blocks.append(BulletListBlock(items=items))
            doc_model.stats.lists += 1
            doc_model.stats.paragraphs += 1
            return

        if _NUMBERED_RE.match(text):
            items = []
            for _, _, spans in lines:
                items.append([self._span_to_run(s) for s in spans if s.get("text", "").strip()])
            blocks.append(NumberedListBlock(items=items))
            doc_model.stats.lists += 1
            doc_model.stats.paragraphs += 1
            return

        runs = [self._span_to_run(s) for _, _, spans in lines for s in spans if s.get("text", "").strip()]
        blocks.append(ParagraphBlock(content=runs))
        doc_model.stats.paragraphs += 1

    def _is_heading(self, text: str, lines: list) -> bool:
        if len(text) > 300:
            return False
        if self._is_bullet(text) or _NUMBERED_RE.match(text):
            return False
        max_size = max(s for _, s, _ in lines)
        return max_size in self._heading_sizes and max_size >= 10.5

    def _heading_level(self, size: float) -> int:
        if len(self._heading_sizes) <= 1:
            return 1
        sorted_sizes = sorted(self._heading_sizes, reverse=True)
        return min(6, sorted_sizes.index(size) + 1)

    @staticmethod
    def _is_bullet(text: str) -> bool:
        stripped = text.lstrip()
        if not stripped:
            return False
        first = stripped[0]
        return first in _BULLET_CHARS or stripped.startswith("\u2022 ")

    @staticmethod
    def _span_to_run(span: dict) -> TextRun:
        flags = span.get("flags", 0)
        return TextRun(
            text=span.get("text", ""),
            bold=bool(flags & 2**4),
            italic=bool(flags & 2**1),
            font_size=round(span.get("size", 0) or 0, 1) or None,
        )
