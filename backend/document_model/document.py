"""The Document root object and conversion reporting types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ConversionWarning(BaseModel):
    """A factual, user-facing note about a conversion limitation."""

    code: str
    message: str
    detail: str | None = None
    severity: Literal["info", "warning"] = "warning"


class DocumentStats(BaseModel):
    """Aggregated counts shown in the conversion report."""

    pages: int = 0
    slides: int = 0
    sheets: int = 0
    paragraphs: int = 0
    headings: int = 0
    lists: int = 0
    tables: int = 0
    images: int = 0
    links: int = 0
    code_blocks: int = 0
    footnotes: int = 0
    comments: int = 0
    charts: int = 0
    ocr_pages: int = 0


class Document(BaseModel):
    """A converted document: metadata, stats and any conversion warnings.

    The MarkItDown engine emits Markdown text directly, so there is no block
    tree here. The typed block hierarchy this model used to carry was left
    unused by that migration and has been removed rather than kept as dead
    weight; the Markdown itself lives on the ConversionContext.
    """

    format: str
    filename: str
    metadata: dict[str, str] = Field(default_factory=dict)
    warnings: list[ConversionWarning] = Field(default_factory=list)
    stats: DocumentStats = Field(default_factory=DocumentStats)
    extra: dict[str, Any] = Field(default_factory=dict)
