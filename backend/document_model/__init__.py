"""Common Document Model - format-independent intermediate representation.

Every converter produces a :class:`Document` made of typed :class:`Block`
objects. The Markdown renderer (and any future renderer) consumes this model,
never the source format directly.
"""

from __future__ import annotations

from document_model.blocks import (
    Block,
    BulletListBlock,
    CaptionBlock,
    CodeBlock,
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
    TableRow,
    TextRun,
)
from document_model.document import ConversionWarning, Document, DocumentStats
from document_model.metadata import normalize_metadata

__all__ = [
    "Block",
    "BulletListBlock",
    "CaptionBlock",
    "CodeBlock",
    "ConversionWarning",
    "Document",
    "DocumentStats",
    "FootnoteBlock",
    "HeadingBlock",
    "HorizontalRuleBlock",
    "ImageBlock",
    "LinkBlock",
    "NumberedListBlock",
    "PageBreakBlock",
    "ParagraphBlock",
    "QuoteBlock",
    "SheetBreakBlock",
    "SlideBreakBlock",
    "TableBlock",
    "TableCell",
    "TableRow",
    "TextRun",
    "normalize_metadata",
]
