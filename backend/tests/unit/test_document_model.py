"""Unit tests for the conversion result model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from document_model import (
    ConversionWarning,
    Document,
    DocumentStats,
    normalize_metadata,
)


class TestDocument:
    def test_build_document(self):
        doc = Document(format="pdf", filename="report.pdf")
        assert doc.format == "pdf"
        assert doc.filename == "report.pdf"
        assert doc.metadata == {}
        assert doc.warnings == []
        assert doc.extra == {}

    def test_has_no_block_tree(self):
        """The MarkItDown engine emits Markdown text, not typed blocks.

        The old block hierarchy went unused after that migration and was
        removed; this guards against it being reintroduced by accident.
        """
        assert "blocks" not in Document.model_fields

    def test_metadata_must_be_strings(self):
        with pytest.raises(ValidationError):
            Document(format="pdf", filename="a.pdf", metadata={"title": object()})

    def test_warnings(self):
        doc = Document(
            format="docx",
            filename="notes.docx",
            warnings=[ConversionWarning(code="ocr_used", message="OCR ran")],
        )
        assert doc.warnings[0].code == "ocr_used"
        assert doc.warnings[0].severity == "warning"

    def test_warning_severity_is_constrained(self):
        with pytest.raises(ValidationError):
            ConversionWarning(code="x", message="y", severity="catastrophic")


class TestDocumentStats:
    def test_defaults_are_zero(self):
        stats = DocumentStats()
        assert stats.pages == 0
        assert stats.images == 0
        assert stats.ocr_pages == 0

    def test_counts_round_trip(self):
        stats = DocumentStats(pages=3, images=2, tables=1)
        assert stats.model_dump()["images"] == 2


class TestMetadata:
    def test_drops_empty_values(self):
        assert normalize_metadata({"title": "  ", "author": "Ada"}) == {"author": "Ada"}

    def test_stringifies_values(self):
        assert normalize_metadata({"pages": 12})["pages"] == "12"
