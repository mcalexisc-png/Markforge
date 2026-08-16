"""Markdown rendering: Common Document Model -> Markdown text.

All Markdown formatting lives here (never in the parsers), so additional
renderers or output formats can be added without touching converters.
"""

from __future__ import annotations

import re

from document_model.blocks import (
    Block,
    BulletListBlock,
    CaptionBlock,
    CodeBlock,
    CommentBlock,
    FootnoteBlock,
    HeadingBlock,
    HorizontalRuleBlock,
    ImageBlock,
    LinkBlock,
    NumberedListBlock,
    PageBreakBlock,
    ParagraphBlock,
    QuoteBlock,
    SheetBreakBlock,
    SlideBreakBlock,
    TableBlock,
    TableCell,
    TextRun,
)
from document_model.document import Document

_ESCAPE_RE = re.compile(r"([\\`*_[\]<>#])")
_PIPE_RE = re.compile(r"\|")
_BLOCKQUOTE_RE = re.compile(r"^>+\s?", re.MULTILINE)


def escape_text(text: str) -> str:
    """Escape Markdown metacharacters in plain text runs."""
    text = text.replace("\\", "\\\\").replace("`", "\\`")
    text = _ESCAPE_RE.sub(r"\\\1", text)
    return text


def escape_table_cell(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    text = text.replace("\n", "<br>")
    text = text.replace("\r", "")
    return text


def escape_url(url: str) -> str:
    return url.replace("\\", "\\\\").replace("(", "%28").replace(")", "%29")


def _plain(block: Block) -> str:
    """Join the text content of a block without Markdown formatting."""
    if isinstance(block, (ParagraphBlock, HeadingBlock, CaptionBlock, QuoteBlock, CommentBlock)):
        return "".join(run.text for run in block.content)
    if isinstance(block, (BulletListBlock, NumberedListBlock)):
        return " ".join("".join(run.text for run in item) for item in block.items)
    if isinstance(block, TableBlock):
        return " ".join(
            " ".join("".join(run.text for run in cell.content) for cell in row.cells)
            for row in block.rows
        )
    return ""


def _inline(runs: list[TextRun]) -> str:
    """Render styled runs inline with emphasis and links."""
    out = []
    for run in runs:
        if not run.text:
            continue
        text = run.text
        if run.href:
            out.append(f"[{escape_text(text)}]({escape_url(run.href)})")
            continue
        if run.code:
            escaped = text.replace("`", "\\`")
            out.append(f"`{escaped}`")
            continue
        token = ""
        if run.bold:
            token += "**"
        if run.italic:
            token += "*"
        if token:
            inner = escape_text(text)
            out.append(f"{token}{inner}{token[::-1]}")
        else:
            out.append(escape_text(text))
    return "".join(out)


def _render_table(block: TableBlock) -> list[str]:
    if not block.rows:
        return []
    col_count = max((len(row.cells) for row in block.rows), default=0)
    if col_count == 0:
        return []
    normalized: list[list[str]] = []
    aligns: list[str | None] = [None] * col_count

    for row in block.rows:
        line: list[str] = []
        for index in range(col_count):
            cell = row.cells[index] if index < len(row.cells) else TableCell(content=[])
            if cell.align:
                aligns[index] = cell.align
            line.append(escape_table_cell("".join(run.text for run in cell.content)))
        normalized.append(line)

    header = normalized[0] if block.has_header else None
    body = normalized[1:] if block.has_header else normalized

    def alignment_row() -> str:
        parts = []
        for index in range(col_count):
            align = aligns[index]
            if align == "center":
                parts.append(":---:")
            elif align == "right":
                parts.append("---:")
            elif align == "left":
                parts.append(":---")
            else:
                parts.append("---")
        return f"|{'|'.join(f' {part} ' for part in parts)}|"

    def row_line(cells: list[str]) -> str:
        return f"|{'|'.join(f' {cell} ' for cell in cells)}|"

    lines: list[str] = []
    if header:
        lines.append(row_line(header))
        lines.append(alignment_row())
    for row in body:
        lines.append(row_line(row))
    return lines


class MarkdownRenderer:
    """Renders a Document to Markdown according to the chosen output mode."""

    def __init__(self, output_mode: str = "fidelity", *, preserve_boundaries: bool = True):
        self.output_mode = output_mode
        self.preserve_boundaries = preserve_boundaries
        self._footnotes: list[tuple[int, str]] = []

    def render(self, doc: Document) -> str:
        lines: list[str] = []
        for block in doc.blocks:
            rendered = self._render_block(block)
            if rendered is not None:
                lines.append(rendered)
        text = "\n\n".join(line for line in lines if line is not None and line.strip())
        if self._footnotes:
            footnotes = "\n".join(f"[^{num}]: {text}" for num, text in self._footnotes)
            text = f"{text}\n\n{footnotes}"
        return self._normalize(text)

    def _render_block(self, block: Block) -> str | None:
        if isinstance(block, HeadingBlock):
            prefix = "#" * block.level
            return f"{prefix} {_inline(block.content)}"
        if isinstance(block, ParagraphBlock):
            return self._render_paragraph(block)
        if isinstance(block, BulletListBlock):
            lines = []
            for item in block.items:
                indent = len(item[0].text.expandtabs()) if item and item[0].text.startswith("\t") else 0
                prefix = "  " * (indent // 2) + "- "
                content = _inline(item)
                lines.append(prefix + content.lstrip())
            return "\n".join(lines)
        if isinstance(block, NumberedListBlock):
            lines = []
            start = block.start or 1
            for index, item in enumerate(block.items, start=start):
                lines.append(f"{index}. {_inline(item)}")
            return "\n".join(lines)
        if isinstance(block, TableBlock):
            return "\n".join(_render_table(block))
        if isinstance(block, ImageBlock):
            if not block.path:
                return None
            alt = block.alt or ""
            caption = block.caption
            result = f"![{escape_text(alt)}]({escape_url(block.path)})"
            if caption:
                result += f"\n\n*{escape_text(caption)}*"
            return result
        if isinstance(block, LinkBlock):
            return f"[{escape_text(_inline(block.content)) if block.content else escape_text(block.href)}]({escape_url(block.href)})"
        if isinstance(block, CodeBlock):
            lang = block.language or ""
            return f"```{lang}\n{block.code.rstrip()}\n```"
        if isinstance(block, QuoteBlock):
            body = "\n".join(
                f"> {_inline([run])}" for run in block.content if run.text.strip()
            )
            return body or None
        if isinstance(block, HorizontalRuleBlock):
            return "---"
        if isinstance(block, CaptionBlock):
            return f"*{_inline(block.content)}*"
        if isinstance(block, FootnoteBlock):
            self._footnotes.append((block.number, _inline(block.content)))
            return f"[^{block.number}]"
        if isinstance(block, CommentBlock):
            author = escape_text(block.author.strip()) if block.author.strip() else "Comment"
            date = block.date.strip()
            header = f"**{author}**" + (f" ({escape_text(date)})" if date else "")
            text = _inline(block.content)
            lines = []
            for part in text.splitlines():
                lines.append(f"> {header}: {part.strip()}" if part.strip() else f"> {header}:")
            return "\n".join(lines) if lines else None
        if isinstance(block, (PageBreakBlock, SlideBreakBlock, SheetBreakBlock)):
            return self._render_break(block)
        return None

    def _render_paragraph(self, block: ParagraphBlock) -> str:
        """Paragraphs split on embedded newlines into separate paragraphs."""
        text = _inline(block.content)
        parts = [part.strip() for part in text.split("\n") if part.strip()]
        if len(parts) <= 1:
            return text
        return "\n\n".join(parts)

    def _render_break(self, block: Block) -> str | None:
        if not self.preserve_boundaries or self.output_mode == "clean":
            return None
        if isinstance(block, PageBreakBlock):
            if block.page_number:
                return f"---\n\n## Page {block.page_number}"
            return "---"
        if isinstance(block, SlideBreakBlock):
            if block.slide_number:
                return f"---\n\n# Slide {block.slide_number}"
            return "---"
        if isinstance(block, SheetBreakBlock):
            return "---"
        return "---"

    def _normalize(self, text: str) -> str:
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def render_document(doc: Document, output_mode: str = "fidelity", *, preserve_boundaries: bool = True) -> str:
    return MarkdownRenderer(output_mode, preserve_boundaries=preserve_boundaries).render(doc)
