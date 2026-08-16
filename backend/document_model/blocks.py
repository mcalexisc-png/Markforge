"""Typed blocks of the Common Document Model.

Blocks are Pydantic models so they validate cleanly, serialize to JSON for
debugging/auditing, and compose into a discriminated union on ``type``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class TextRun(BaseModel):
    """A run of styled text within a block."""

    text: str = ""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    code: bool = False
    href: str | None = None
    font_size: float | None = None


class Block(BaseModel):
    """Base class for every document block."""

    type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class HeadingBlock(Block):
    type: Literal["heading"] = "heading"
    level: int = Field(default=1, ge=1, le=6)
    content: list[TextRun] = Field(default_factory=list)


class ParagraphBlock(Block):
    type: Literal["paragraph"] = "paragraph"
    content: list[TextRun] = Field(default_factory=list)


class BulletListBlock(Block):
    type: Literal["bullet_list"] = "bullet_list"
    items: list[list[TextRun]] = Field(default_factory=list)


class NumberedListBlock(Block):
    type: Literal["numbered_list"] = "numbered_list"
    items: list[list[TextRun]] = Field(default_factory=list)
    start: int | None = None


class TableCell(BaseModel):
    content: list[TextRun] = Field(default_factory=list)
    rowspan: int = 1
    colspan: int = 1
    align: Literal["left", "center", "right"] | None = None


class TableRow(BaseModel):
    cells: list[TableCell] = Field(default_factory=list)


class TableBlock(Block):
    type: Literal["table"] = "table"
    rows: list[TableRow] = Field(default_factory=list)
    has_header: bool = False
    caption: str | None = None


class ImageBlock(Block):
    type: Literal["image"] = "image"
    path: str = ""  # relative to the output directory, e.g. assets/image-001.png
    alt: str = ""
    caption: str | None = None


class LinkBlock(Block):
    type: Literal["link"] = "link"
    href: str = ""
    content: list[TextRun] = Field(default_factory=list)


class CodeBlock(Block):
    type: Literal["code_block"] = "code_block"
    language: str | None = None
    code: str = ""


class QuoteBlock(Block):
    type: Literal["quote"] = "quote"
    content: list[TextRun] = Field(default_factory=list)


class HorizontalRuleBlock(Block):
    type: Literal["horizontal_rule"] = "horizontal_rule"


class PageBreakBlock(Block):
    type: Literal["page_break"] = "page_break"
    page_number: int | None = None


class SlideBreakBlock(Block):
    type: Literal["slide_break"] = "slide_break"
    slide_number: int | None = None


class SheetBreakBlock(Block):
    type: Literal["sheet_break"] = "sheet_break"
    sheet_number: int | None = None
    sheet_name: str | None = None


class CaptionBlock(Block):
    type: Literal["caption"] = "caption"
    content: list[TextRun] = Field(default_factory=list)


class FootnoteBlock(Block):
    type: Literal["footnote"] = "footnote"
    number: int = 0
    content: list[TextRun] = Field(default_factory=list)


class CommentBlock(Block):
    """A review comment or annotation anchored to the surrounding content."""

    type: Literal["comment"] = "comment"
    content: list[TextRun] = Field(default_factory=list)
    author: str = ""
    date: str = ""


BlockUnion = Annotated[
    HeadingBlock | ParagraphBlock | BulletListBlock | NumberedListBlock | TableBlock | ImageBlock | LinkBlock | CodeBlock | QuoteBlock | HorizontalRuleBlock | PageBreakBlock | SlideBreakBlock | SheetBreakBlock | CaptionBlock | FootnoteBlock | CommentBlock,
    Field(discriminator="type"),
]
