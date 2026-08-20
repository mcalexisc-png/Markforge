"""Unit tests for the MarkItDown conversion engine adapter."""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.make_fixtures import (
    make_deck_pdf,
    make_docx,
    make_pdf,
    make_pptx,
    make_scanned_pdf,
    make_two_column_pdf,
    make_xlsx,
)

from app.schemas.settings import ConversionSettings
from converters.base import ConversionContext
from converters.markitdown import convert_with_markitdown
from document_model.document import Document


def make_context(source: Path, tmp_path: Path, **overrides) -> ConversionContext:
    output_dir = tmp_path / "out"
    output_dir.mkdir(exist_ok=True)
    return ConversionContext(
        source_path=source,
        settings=ConversionSettings(**overrides),
        output_dir=output_dir,
    )


def assert_text_only(markdown: str) -> None:
    assert markdown
    assert "![" not in markdown
    assert "assets/" not in markdown


class TestMarkitdownEngine:
    def test_pdf_conversion(self, tmp_path: Path):
        source = make_pdf(tmp_path / "report.pdf", pages=3)
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        assert isinstance(doc, Document)
        assert doc.format == "pdf"
        assert context.markdown_output
        assert_text_only(context.markdown_output)
        assert doc.stats.headings >= 0
        assert len(doc.warnings) == 0

    def test_docx_conversion(self, tmp_path: Path):
        source = make_docx(tmp_path / "letter.docx")
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        assert doc.format == "docx"
        assert context.markdown_output
        assert_text_only(context.markdown_output)

    def test_pptx_conversion(self, tmp_path: Path):
        source = make_pptx(tmp_path / "deck.pptx", slides=3)
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        assert doc.format == "pptx"
        assert context.markdown_output
        assert_text_only(context.markdown_output)

    def test_xlsx_conversion(self, tmp_path: Path):
        source = make_xlsx(tmp_path / "book.xlsx", sheets=2)
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        assert doc.format == "xlsx"
        assert context.markdown_output
        assert_text_only(context.markdown_output)

    def test_pptx_pictures_become_placeholders(self, tmp_path: Path):
        from io import BytesIO

        from PIL import Image
        from pptx import Presentation

        source = tmp_path / "pics.pptx"
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = "Pictures"
        buffer = BytesIO()
        Image.new("RGB", (16, 16), (200, 30, 30)).save(buffer, format="PNG")
        buffer.seek(0)
        slide.shapes.add_picture(buffer, 0, 0)
        prs.save(source)

        context = make_context(source, tmp_path)
        convert_with_markitdown(context)
        out = context.markdown_output
        assert out
        assert "![" not in out
        assert "].jpg" not in out
        assert "[Image: image.png]" in out

    def test_stats_count_pages_slides_sheets(self, tmp_path: Path):
        pdf = make_deck_pdf(tmp_path / "deck.pdf")
        pdf_context = make_context(pdf, tmp_path, ocr_mode="auto")
        pdf_doc = convert_with_markitdown(pdf_context)
        assert pdf_doc.stats.pages == 4

        pptx = make_pptx(tmp_path / "slides.pptx", slides=3)
        pptx_context = make_context(pptx, tmp_path)
        pptx_doc = convert_with_markitdown(pptx_context)
        assert pptx_doc.stats.slides == 3

        xlsx = make_xlsx(tmp_path / "book.xlsx", sheets=2)
        xlsx_context = make_context(xlsx, tmp_path)
        xlsx_doc = convert_with_markitdown(xlsx_context)
        assert xlsx_doc.stats.sheets == 2

    def test_ocr_never_still_marks_textless_pages(self, tmp_path: Path):
        source = make_scanned_pdf(tmp_path / "scan.pdf", pages=1)
        context = make_context(source, tmp_path, ocr_mode="never")
        doc = convert_with_markitdown(context)
        assert not context.ocr_used
        assert "[Image page — no text]" in context.markdown_output
        assert not any(w.code == "ocr_unavailable" for w in doc.warnings)

    def test_ocr_unavailable_warning(self, tmp_path: Path, monkeypatch):
        import converters.markitdown as mod

        monkeypatch.setattr(mod, "tesseract_available", lambda: False)
        source = make_scanned_pdf(tmp_path / "scan.pdf")
        context = make_context(source, tmp_path, ocr_mode="auto")
        doc = convert_with_markitdown(context)
        codes = [w.code for w in doc.warnings]
        assert "ocr_unavailable" in codes
        assert not context.ocr_used

    def test_ocr_prepass_runs_when_available(self, tmp_path: Path):
        from app.services.ocr import tesseract_available

        if not tesseract_available():
            pytest.skip("tesseract not installed on this system")

        source = make_scanned_pdf(tmp_path / "scan2.pdf")
        context = make_context(source, tmp_path, ocr_mode="auto")
        doc = convert_with_markitdown(context)
        codes = [w.code for w in doc.warnings]
        assert "ocr_used" in codes
        assert context.ocr_used
        assert doc.stats.ocr_pages >= 1

    def test_ocr_never_skips_prepass(self, tmp_path: Path, monkeypatch):
        import converters.markitdown as mod

        monkeypatch.setattr(mod, "tesseract_available", lambda: True)
        source = make_scanned_pdf(tmp_path / "scan3.pdf")
        context = make_context(source, tmp_path, ocr_mode="never")
        doc = convert_with_markitdown(context)
        assert not context.ocr_used
        assert not any(w.code == "ocr_unavailable" for w in doc.warnings)

    def test_ocr_always_forces_prepass_without_detection(self, tmp_path: Path, monkeypatch):
        import converters.markitdown as mod

        calls: list[bool] = []

        def fake_detect(source) -> bool:
            raise AssertionError("detection must be bypassed in 'always' mode")

        def fake_ocr(source, context, *, force_ocr):
            calls.append(force_ocr)
            return None

        monkeypatch.setattr(mod, "_detect_scanned_pdf", fake_detect)
        monkeypatch.setattr(mod, "tesseract_available", lambda: True)
        monkeypatch.setattr(mod, "_ocr_pdf_copy", fake_ocr)

        source = make_pdf(tmp_path / "plain.pdf", pages=2)
        context = make_context(source, tmp_path, ocr_mode="always")
        convert_with_markitdown(context)
        assert calls == [True]

    def test_ocr_auto_skips_prepass_when_not_scanned(self, tmp_path: Path, monkeypatch):
        import converters.markitdown as mod

        calls: list[bool] = []

        def fake_ocr(source, context, *, force_ocr):
            calls.append(force_ocr)
            return None

        monkeypatch.setattr(mod, "_detect_scanned_pdf", lambda source: False)
        monkeypatch.setattr(mod, "tesseract_available", lambda: True)
        monkeypatch.setattr(mod, "_ocr_pdf_copy", fake_ocr)

        source = make_pdf(tmp_path / "plain2.pdf", pages=2)
        context = make_context(source, tmp_path, ocr_mode="auto")
        convert_with_markitdown(context)
        assert calls == []
        assert not context.ocr_used


class TestColumnAwarePdf:
    def test_columns_not_interleaved(self, tmp_path: Path):
        source = make_two_column_pdf(tmp_path / "cols.pdf")
        context = make_context(source, tmp_path, ocr_mode="never")
        convert_with_markitdown(context)
        md = context.markdown_output
        assert "Left column line A\nLeft column line B\nLeft column line C" in md
        assert md.index("Left column line A") < md.index("Right column line A")

    def test_large_font_promoted_to_heading(self, tmp_path: Path):
        source = make_pdf(tmp_path / "headings.pdf", pages=2)
        context = make_context(source, tmp_path, ocr_mode="never")
        convert_with_markitdown(context)
        md = context.markdown_output
        assert "## Chapter 1" in md
        assert "## Paragraph text on page 1." not in md

    def test_page_markers_kept_in_fidelity(self, tmp_path: Path):
        source = make_pdf(tmp_path / "markers.pdf", pages=2)
        context = make_context(source, tmp_path, ocr_mode="never", output_mode="fidelity")
        convert_with_markitdown(context)
        assert "<!-- Page 1 -->" in context.markdown_output
        assert "<!-- Page 2 -->" in context.markdown_output

    def test_page_markers_stripped_in_clean(self, tmp_path: Path):
        source = make_pdf(tmp_path / "markers2.pdf", pages=2)
        context = make_context(source, tmp_path, ocr_mode="never", output_mode="clean")
        convert_with_markitdown(context)
        assert "<!-- Page" not in context.markdown_output

    def test_checkmark_merged_with_following_line(self, tmp_path: Path):
        import os

        import pymupdf

        symbol_font = r"C:\Windows\Fonts\seguisym.ttf"
        if not os.path.exists(symbol_font):
            pytest.skip("Segoe UI Symbol font not available")

        source = tmp_path / "checks.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_font(fontname="f-sym", fontfile=symbol_font)
        page.insert_text((72, 72), "Task list", fontsize=14)
        page.insert_text((72, 110), "✔", fontname="f-sym", fontsize=12)
        page.insert_text((72, 130), "Understand the material", fontsize=12)
        doc.save(source)
        doc.close()
        context = make_context(source, tmp_path, ocr_mode="never")
        convert_with_markitdown(context)
        md = context.markdown_output
        assert "✔ Understand the material" in md

    def test_standalone_bullet_and_number_merged(self, tmp_path: Path):
        import pymupdf

        source = tmp_path / "list.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Steps", fontsize=14)
        page.insert_text((72, 110), "1.", fontsize=12)
        page.insert_text((72, 132), "Humanap ng taong pinagkakatiwalaan.", fontsize=12)
        page.insert_text((72, 160), "2.", fontsize=12)
        page.insert_text((72, 182), "I-dokumento ang insidente.", fontsize=12)
        doc.save(source)
        doc.close()
        context = make_context(source, tmp_path, ocr_mode="never")
        convert_with_markitdown(context)
        md = context.markdown_output
        assert "1. Humanap ng taong pinagkakatiwalaan." in md
        assert "2. I-dokumento ang insidente." in md
        assert "\n1.\n" not in md

    def test_placeholder_single_brackets(self, tmp_path: Path):
        source = make_deck_pdf(tmp_path / "deck.pdf")
        context = make_context(source, tmp_path, ocr_mode="never")
        convert_with_markitdown(context)
        md = context.markdown_output
        assert "[Slide image — no text]" in md
        assert "[[Slide image — no text]]" not in md


class TestDuplicatePages:
    def test_duplicates_removed_with_warning(self, tmp_path: Path):
        source = make_deck_pdf(tmp_path / "deck.pdf")
        context = make_context(source, tmp_path, ocr_mode="never")
        doc = convert_with_markitdown(context)
        codes = [w.code for w in doc.warnings]
        assert "duplicate_pages_removed" in codes
        md = context.markdown_output
        assert md.count("Mission 3") == 1

    def test_identical_textless_pages_not_deduplicated(self, tmp_path: Path):
        from tests.fixtures.make_fixtures import make_scanned_pdf

        source = make_scanned_pdf(tmp_path / "scans.pdf", pages=3)
        context = make_context(source, tmp_path, ocr_mode="never")
        doc = convert_with_markitdown(context)
        assert not any(w.code == "duplicate_pages_removed" for w in doc.warnings)


class TestDeckVsScanOcr:
    def test_deck_mode_skips_ocr_with_placeholder(self, tmp_path: Path, monkeypatch):
        import converters.markitdown as mod

        def fail_ocr(*args, **kwargs):
            raise AssertionError("OCR must not run in deck mode")

        monkeypatch.setattr(mod, "_ocr_pdf_copy", fail_ocr)
        source = make_deck_pdf(tmp_path / "deck2.pdf")
        context = make_context(source, tmp_path, ocr_mode="auto")
        doc = convert_with_markitdown(context)
        assert not context.ocr_used
        codes = [w.code for w in doc.warnings]
        assert "decorative_pages_skipped" in codes
        assert "[Slide image — no text]" in context.markdown_output

    def test_scan_mode_ocrs_all_pages(self, tmp_path: Path, monkeypatch):
        import converters.markitdown as mod

        calls: list[bool] = []

        def record_ocr(source, context, *, force_ocr):
            calls.append(force_ocr)
            return None

        monkeypatch.setattr(mod, "_ocr_pdf_copy", record_ocr)
        monkeypatch.setattr(mod, "tesseract_available", lambda: True)
        source = make_scanned_pdf(tmp_path / "scan4.pdf", pages=2)
        context = make_context(source, tmp_path, ocr_mode="auto")
        convert_with_markitdown(context)
        assert calls == [False]
        assert not context.ocr_used


class TestPptxHeadings:
    def test_large_font_text_box_promoted(self, tmp_path: Path):
        from pptx import Presentation
        from pptx.util import Pt

        source = tmp_path / "deck.pptx"
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        title_box = slide.shapes.add_textbox(0, 0, 9_000_000, 1_000_000)
        title_box.text_frame.text = "Big Mission Title"
        title_box.text_frame.paragraphs[0].runs[0].font.size = Pt(40)
        body_box = slide.shapes.add_textbox(0, 2_000_000, 9_000_000, 3_000_000)
        body_box.text_frame.text = "Normal body text"
        body_box.text_frame.paragraphs[0].runs[0].font.size = Pt(18)
        prs.save(source)

        context = make_context(source, tmp_path)
        convert_with_markitdown(context)
        md = context.markdown_output
        assert "## Big Mission Title" in md
        assert "## Normal body text" not in md

    def test_title_placeholder_still_promoted(self, tmp_path: Path):
        source = make_pptx(tmp_path / "deck2.pptx", slides=2)
        context = make_context(source, tmp_path)
        convert_with_markitdown(context)
        md = context.markdown_output
        assert "# Introduction" in md