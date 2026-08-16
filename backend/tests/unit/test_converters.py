"""Unit tests for the format converters and the conversion pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.make_fixtures import (
    make_docx,
    make_docx_reviewed,
    make_pdf,
    make_pptx,
    make_pptx_charts,
    make_text_pdf_with_image,
    make_two_column_pdf,
    make_xlsx,
    make_xlsx_charts,
)

from app.schemas.settings import ConversionSettings
from converters.base import ConversionContext
from converters.registry import create_converter, detect_format
from document_model.blocks import (
    CommentBlock,
    PageBreakBlock,
    TableBlock,
)
from markdown.renderer import render_document


def make_context(source: Path, tmp_path: Path, **overrides) -> ConversionContext:
    output_dir = tmp_path / "out"
    output_dir.mkdir(exist_ok=True)
    return ConversionContext(
        source_path=source,
        settings=ConversionSettings(**overrides),
        output_dir=output_dir,
    )


class TestRegistry:
    def test_detect(self):
        assert detect_format("a.pdf") == "pdf"
        assert detect_format("b.DOCX") == "docx"
        assert detect_format("c.pptx") == "pptx"
        assert detect_format("d.xlsx") == "xlsx"

    def test_unsupported(self):
        with pytest.raises(Exception) as exc:
            detect_format("e.txt")
        assert "not supported" in str(exc.value)

    def test_allowed_extensions(self):
        from converters.registry import ALLOWED_EXTENSIONS

        assert set(ALLOWED_EXTENSIONS) == {".pdf", ".docx", ".pptx", ".xlsx"}


class TestPdfConverter:
    def test_basic_conversion(self, tmp_path: Path):
        source = make_pdf(tmp_path / "report.pdf", pages=3)
        doc = create_converter(make_context(source, tmp_path)).convert()
        assert doc.format == "pdf"
        assert doc.metadata["title"] == "Test Report"
        assert doc.stats.pages == 3
        assert doc.stats.headings >= 1
        assert doc.stats.paragraphs >= 3
        has_breaks = any(isinstance(b, PageBreakBlock) for b in doc.blocks)
        assert has_breaks

    def test_links(self, tmp_path: Path):
        source = make_pdf(tmp_path / "links.pdf")
        doc = create_converter(make_context(source, tmp_path)).convert()
        assert doc.stats.links >= 1

    def test_image_extraction(self, tmp_path: Path):
        source = make_text_pdf_with_image(tmp_path / "img.pdf")
        context = make_context(source, tmp_path)
        doc = create_converter(context).convert()
        assert doc.stats.images >= 1
        assert context.asset_dir.exists()
        assets = list(context.asset_dir.iterdir())
        assert len(assets) == 1

    def test_no_image_extraction_when_disabled(self, tmp_path: Path):
        source = make_text_pdf_with_image(tmp_path / "img2.pdf")
        context = make_context(source, tmp_path, extract_images=False)
        doc = create_converter(context).convert()
        assert doc.stats.images == 0

    def test_clean_mode_renders(self, tmp_path: Path):
        source = make_pdf(tmp_path / "clean.pdf")
        context = make_context(source, tmp_path, output_mode="clean")
        doc = create_converter(context).convert()
        markdown = render_document(doc, output_mode="clean")
        assert "Page 1" not in markdown
        assert "Chapter" in markdown

    def test_scanned_pdf_no_ocr_engine(self, tmp_path: Path):
        from fixtures.make_fixtures import make_scanned_pdf

        source = make_scanned_pdf(tmp_path / "scanned.pdf")
        context = make_context(source, tmp_path)
        converted = create_converter(context).convert()
        codes = {w["code"] for w in converted.warnings}
        assert "ocr_unavailable" in codes

    def test_two_column_reading_order(self, tmp_path: Path):
        source = make_two_column_pdf(tmp_path / "columns.pdf")
        doc = create_converter(make_context(source, tmp_path)).convert()
        markdown = render_document(doc)
        header = markdown.index("Report header spanning both columns")
        left_c = markdown.index("Left column line C")
        right_a = markdown.index("Right column line A")
        assert header < left_c < right_a
        assert "Left column line A" in markdown
        assert "Right column line C" in markdown


class TestDocxConverter:
    def test_structure(self, tmp_path: Path):
        source = make_docx(tmp_path / "notes.docx")
        doc = create_converter(make_context(source, tmp_path)).convert()
        assert doc.format == "docx"
        assert doc.stats.headings >= 2
        assert doc.stats.tables >= 1
        assert doc.stats.lists >= 2
        assert doc.stats.links >= 1
        has_bold = any(
            run.bold
            for b in doc.blocks
            if hasattr(b, "content")
            for run in (b.content if isinstance(b.content, list) else [])
            if hasattr(run, "bold")
        )
        assert has_bold
        markdown = render_document(doc)
        assert "| Name | Value |" in markdown
        assert "**Bold text" in markdown

    def test_comments_and_tracked_changes(self, tmp_path: Path):
        source = make_docx_reviewed(tmp_path / "reviewed.docx")
        doc = create_converter(make_context(source, tmp_path)).convert()
        assert doc.stats.comments == 1
        comments = [b for b in doc.blocks if isinstance(b, CommentBlock)]
        assert len(comments) == 1
        assert comments[0].author == "Reviewer"
        assert "Needs a citation." in "".join(r.text for r in comments[0].content)
        markdown = render_document(doc)
        assert "**Reviewer**" in markdown
        assert "Needs a citation." in markdown
        assert "Inserted sentence" in markdown
        assert "Removed sentence" not in markdown
        codes = {w["code"] for w in doc.warnings}
        assert "tracked_changes" in codes


class TestPptxConverter:
    def test_slides_and_notes(self, tmp_path: Path):
        source = make_pptx(tmp_path / "deck.pptx", slides=3)
        doc = create_converter(make_context(source, tmp_path)).convert()
        assert doc.format == "pptx"
        assert doc.stats.slides == 3
        assert doc.stats.headings >= 3
        assert any(b.type == "quote" for b in doc.blocks)  # speaker notes
        markdown = render_document(doc, output_mode="fidelity")
        assert "# Slide 1" in markdown
        assert "# Slide 2" in markdown

    def test_clean_drops_slide_boundaries(self, tmp_path: Path):
        source = make_pptx(tmp_path / "deck2.pptx")
        doc = create_converter(make_context(source, tmp_path)).convert()
        markdown = render_document(doc, output_mode="clean")
        assert "# Slide 1" not in markdown

    def test_chart_data_extracted(self, tmp_path: Path):
        source = make_pptx_charts(tmp_path / "charts.pptx", slides=2)
        doc = create_converter(make_context(source, tmp_path)).convert()
        assert doc.stats.charts == 2
        assert doc.stats.tables >= 2
        markdown = render_document(doc)
        assert "Revenue" in markdown
        assert "Costs" in markdown
        assert "Q1" in markdown
        assert "Speaker notes" in markdown


class TestXlsxConverter:
    def test_sheets_and_tables(self, tmp_path: Path):
        source = make_xlsx(tmp_path / "grades.xlsx")
        doc = create_converter(make_context(source, tmp_path)).convert()
        assert doc.format == "xlsx"
        assert doc.stats.sheets == 2
        assert doc.stats.tables >= 2
        assert doc.stats.headings >= 2
        tables = [b for b in doc.blocks if isinstance(b, TableBlock)]
        assert any(b.has_header for b in tables)
        assert doc.metadata["title"] == "grades"
        markdown = render_document(doc)
        assert "| Name | Age | Grade |" in markdown
        assert "| John | 20 | A |" in markdown

    def test_merged_cells_warning(self, tmp_path: Path):
        source = make_xlsx(tmp_path / "merged.xlsx")
        doc = create_converter(make_context(source, tmp_path)).convert()
        codes = {w["code"] for w in doc.warnings}
        assert "merged_cells" in codes

    def test_numeric_alignment(self, tmp_path: Path):
        source = make_xlsx(tmp_path / "aligned.xlsx")
        doc = create_converter(make_context(source, tmp_path)).convert()
        markdown = render_document(doc)
        assert "|---:|" in markdown or "---:" in markdown

    def test_chart_and_comment_extraction(self, tmp_path: Path):
        source = make_xlsx_charts(tmp_path / "charts.xlsx")
        doc = create_converter(make_context(source, tmp_path)).convert()
        assert doc.stats.charts == 1
        assert doc.stats.comments == 1
        markdown = render_document(doc)
        assert "Revenue vs costs" in markdown
        assert "Starts below expectations." in markdown
        assert "Q1" in markdown


class TestPipeline:
    def test_deterministic_output(self, tmp_path: Path):
        source = make_pdf(tmp_path / "det.pdf", pages=2)
        context_a = make_context(source, tmp_path)
        context_b = make_context(source, tmp_path)
        md_a = render_document(create_converter(context_a).convert())
        md_b = render_document(create_converter(context_b).convert())
        assert md_a == md_b

    def test_no_content_invention(self, tmp_path: Path):
        source = make_pdf(tmp_path / "honest.pdf", pages=1)
        doc = create_converter(make_context(source, tmp_path)).convert()
        markdown = render_document(doc)
        assert "Chapter 1" in markdown
        assert "Page 1" in markdown  # fidelity heading, not invented text
