"""Unit tests for the Common Document Model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from document_model import (
    ConversionWarning,
    Document,
    HeadingBlock,
    PageBreakBlock,
    ParagraphBlock,
    TableBlock,
    TableCell,
    TableRow,
    TextRun,
)


class TestDocumentModel:
    def test_build_document(self):
        doc = Document(
            format="pdf",
            filename="a.pdf",
            metadata={"title": "T"},
            blocks=[
                HeadingBlock(level=1, content=[TextRun(text="Title")]),
                ParagraphBlock(content=[TextRun(text="Body", bold=True)]),
            ],
        )
        assert doc.blocks[0].type == "heading"
        assert doc.blocks[0].level == 1
        assert doc.blocks[1].content[0].bold is True

    def test_discriminated_union(self):
        doc = Document(
            format="docx",
            filename="a.docx",
            blocks=[
                {"type": "page_break", "page_number": 3},
                {"type": "paragraph", "content": [{"text": "hi"}]},
            ],
        )
        assert isinstance(doc.blocks[0], PageBreakBlock)
        assert doc.blocks[0].page_number == 3
        assert isinstance(doc.blocks[1], ParagraphBlock)

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            Document(
                format="x",
                filename="a",
                blocks=[{"type": "mystery_block"}],
            )

    def test_warnings(self):
        doc = Document(format="pdf", filename="a.pdf")
        doc.warnings.append(
            ConversionWarning(code="chart", message="Chart skipped", severity="warning")
        )
        assert doc.warnings[0].code == "chart"

    def test_stats_defaults(self):
        doc = Document(format="pdf", filename="a.pdf")
        assert doc.stats.pages == 0
        assert doc.stats.tables == 0

    def test_table_model(self):
        table = TableBlock(
            rows=[
                TableRow(cells=[TableCell(content=[TextRun(text="A")]), TableCell(content=[TextRun(text="1")], align="right")]),
            ],
            has_header=True,
        )
        assert table.rows[0].cells[1].align == "right"
