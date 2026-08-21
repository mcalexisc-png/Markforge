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


def assert_no_figures(markdown: str) -> None:
    """These fixtures embed no images, so no figure should be referenced.

    Image extraction is on by default, so this now guards against inventing
    references rather than against extraction itself. Figure extraction has its
    own coverage in :class:`TestImageExtraction`.
    """
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
        assert_no_figures(context.markdown_output)
        assert doc.stats.headings >= 0
        assert len(doc.warnings) == 0

    def test_docx_conversion(self, tmp_path: Path):
        source = make_docx(tmp_path / "letter.docx")
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        assert doc.format == "docx"
        assert context.markdown_output
        assert_no_figures(context.markdown_output)

    def test_pptx_conversion(self, tmp_path: Path):
        source = make_pptx(tmp_path / "deck.pptx", slides=3)
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        assert doc.format == "pptx"
        assert context.markdown_output
        assert_no_figures(context.markdown_output)

    def test_xlsx_conversion(self, tmp_path: Path):
        source = make_xlsx(tmp_path / "book.xlsx", sheets=2)
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        assert doc.format == "xlsx"
        assert context.markdown_output
        assert_no_figures(context.markdown_output)

    def test_pptx_pictures_become_placeholders_when_extraction_is_off(
        self, tmp_path: Path
    ):
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

        context = make_context(source, tmp_path, extract_images=False)
        convert_with_markitdown(context)
        out = context.markdown_output
        assert out
        assert "![" not in out
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

    def test_ocr_unavailable_warning_when_package_missing(self, tmp_path: Path, monkeypatch):
        import converters.markitdown as mod

        monkeypatch.setattr(mod, "tesseract_available", lambda: True)
        monkeypatch.setattr(mod, "_ocrmypdf_importable", lambda: False)
        source = make_scanned_pdf(tmp_path / "scan-missing-pkg.pdf")
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

def _write(path: Path, data: bytes | str) -> Path:
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return path


def make_epub(path: Path) -> Path:
    """Minimal but valid EPUB 3 package."""
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
            'version="3.0" unique-identifier="id"><metadata '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test Book</dc:title>'
            "<dc:creator>An Author</dc:creator>"
            '<dc:identifier id="id">urn:uuid:1</dc:identifier>'
            "<dc:language>en</dc:language></metadata><manifest>"
            '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest><spine><itemref idref="c1"/></spine></package>',
        )
        archive.writestr(
            "OEBPS/c1.xhtml",
            '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body>'
            "<h1>Chapter One</h1><p>Body text of the chapter.</p></body></html>",
        )
    return path


class TestExpandedFormats:
    """Every extension in ALLOWED_EXTENSIONS must actually convert.

    The allowlist and the registered converters are two halves of one contract;
    widening one without the other fails at conversion time instead of upload.
    """

    @pytest.mark.parametrize(
        ("name", "content", "expected"),
        [
            ("page.html", "<html><body><h1>Title</h1><p>Body</p></body></html>", "# Title"),
            ("page.htm", "<html><body><h2>Sub</h2></body></html>", "## Sub"),
            ("notes.txt", "plain text line\nsecond line\n", "plain text line"),
            ("notes.md", "# Heading\n\n- a\n- b\n", "# Heading"),
            ("data.csv", "name,score\nAda,99\nGrace,100\n", "| Ada | 99 |"),
            ("data.tsv", "name\tscore\nAda\t99\n", "Ada"),
            ("data.json", '{"a": 1, "b": [1, 2]}', '"a"'),
            ("data.xml", "<?xml version='1.0'?><root><item>x</item></root>", "item"),
        ],
    )
    def test_text_family_converts(self, tmp_path: Path, name, content, expected):
        source = _write(tmp_path / name, content)
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        assert isinstance(doc, Document)
        assert expected in context.markdown_output

    def test_ipynb_converts_cells(self, tmp_path: Path):
        import json

        notebook = {
            "cells": [
                {"cell_type": "markdown", "metadata": {}, "source": ["# NB Title"]},
                {
                    "cell_type": "code",
                    "execution_count": 1,
                    "metadata": {},
                    "outputs": [],
                    "source": ["print('hi')"],
                },
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                }
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        source = _write(tmp_path / "nb.ipynb", json.dumps(notebook))
        context = make_context(source, tmp_path)
        convert_with_markitdown(context)
        assert "# NB Title" in context.markdown_output
        assert "print('hi')" in context.markdown_output

    def test_epub_converts_with_metadata(self, tmp_path: Path):
        source = make_epub(tmp_path / "book.epub")
        context = make_context(source, tmp_path)
        convert_with_markitdown(context)
        assert "Test Book" in context.markdown_output
        assert "Chapter One" in context.markdown_output


def _png(width: int, height: int, color=(40, 120, 200)) -> bytes:
    from io import BytesIO

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), color)
    # A little internal structure so the file does not compress to nothing and
    # trip the MIN_BYTES branch of the decorative filter.
    ImageDraw.Draw(image).ellipse(
        (width * 0.1, height * 0.1, width * 0.9, height * 0.9), fill=(250, 210, 70)
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_figure_pdf(path: Path, pages: int = 2, decorations: bool = True) -> Path:
    """A PDF with one real figure per page, plus decorative noise."""
    import pymupdf

    doc = pymupdf.open()
    for number in range(1, pages + 1):
        page = doc.new_page()
        page.insert_text((72, 72), f"Chapter {number}: findings and discussion")
        page.insert_image(
            pymupdf.Rect(72, 110, 400, 350),
            stream=_png(500, 360, (20, 80 + number * 30, 190)),
        )
        if decorations:
            # A hairline rule and a spacer pixel: both must be filtered out.
            page.insert_image(
                pymupdf.Rect(72, 700, 500, 703), stream=_png(600, 4, (10, 10, 10))
            )
            page.insert_image(
                pymupdf.Rect(520, 40, 523, 43), stream=_png(3, 3, (10, 10, 10))
            )
    doc.save(path)
    doc.close()
    return path


class TestImageExtraction:
    def test_pdf_figures_are_anchored_to_their_page(self, tmp_path: Path):
        source = make_figure_pdf(tmp_path / "figures.pdf", pages=3)
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)

        assert doc.stats.images == 3
        out = context.markdown_output
        for page_number in (1, 2, 3):
            marker = f"<!-- Page {page_number} -->"
            after = out.index(marker) + len(marker)
            # The figure must follow its own page marker, before the next one.
            nxt = out.find("<!-- Page ", after)
            segment = out[after:] if nxt == -1 else out[after:nxt]
            assert "](assets/" in segment, f"page {page_number} lost its figure"

    def test_decorative_images_are_filtered_out(self, tmp_path: Path):
        source = make_figure_pdf(tmp_path / "noisy.pdf", pages=2)
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        # Two real figures; the rules and spacer pixels must not survive.
        assert doc.stats.images == 2

    def test_assets_are_written_to_the_output_directory(self, tmp_path: Path):
        source = make_figure_pdf(tmp_path / "figures.pdf", pages=2)
        context = make_context(source, tmp_path)
        convert_with_markitdown(context)

        assets = sorted((context.output_dir / "assets").glob("*"))
        assert [a.name for a in assets] == ["image-001.png", "image-002.png"]
        assert all(a.stat().st_size > 0 for a in assets)

    def test_repeated_image_is_saved_once(self, tmp_path: Path):
        """A logo on every page should cost one file, not one per page."""
        import pymupdf

        logo = _png(300, 200, (90, 90, 200))
        source = tmp_path / "logo.pdf"
        doc = pymupdf.open()
        for number in range(1, 5):
            page = doc.new_page()
            # Unique text per page, or the duplicate-page pre-pass collapses
            # them and this stops testing image dedup at all.
            page.insert_text((72, 72), f"Section {number} body text")
            page.insert_image(pymupdf.Rect(72, 100, 272, 233), stream=logo)
        doc.save(source)
        doc.close()

        context = make_context(source, tmp_path)
        convert_with_markitdown(context)
        assets = list((context.output_dir / "assets").glob("*"))
        assert len(assets) == 1
        assert context.markdown_output.count("](assets/") == 4

    def test_extraction_can_be_turned_off(self, tmp_path: Path):
        source = make_figure_pdf(tmp_path / "figures.pdf", pages=2)
        context = make_context(source, tmp_path, extract_images=False)
        doc = convert_with_markitdown(context)

        assert doc.stats.images == 0
        assert "](assets/" not in context.markdown_output
        assert not (context.output_dir / "assets").exists()

    def test_figures_survive_preserve_links_off(self, tmp_path: Path):
        """Turning off links must not silently delete the document's figures."""
        source = make_figure_pdf(tmp_path / "figures.pdf", pages=2)
        context = make_context(source, tmp_path, preserve_links=False)
        doc = convert_with_markitdown(context)
        assert doc.stats.images == 2

    def test_extraction_reports_a_warning(self, tmp_path: Path):
        source = make_figure_pdf(tmp_path / "figures.pdf", pages=2)
        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        assert any(w.code == "images_extracted" for w in doc.warnings)

    def test_docx_figures_are_placed_inline(self, tmp_path: Path):
        from io import BytesIO

        import docx
        from docx.shared import Inches

        source = tmp_path / "report.docx"
        document = docx.Document()
        document.add_heading("Report", level=1)
        document.add_paragraph("Before the figure.")
        document.add_picture(BytesIO(_png(520, 340)), width=Inches(4))
        document.add_paragraph("Between the figures.")
        document.add_picture(BytesIO(_png(500, 320, (40, 160, 90))), width=Inches(4))
        document.add_paragraph("After the figure.")
        document.save(source)

        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        out = context.markdown_output

        assert doc.stats.images == 2
        # Inline placement: each figure sits between its neighbouring paragraphs.
        assert out.index("Before the figure.") < out.index("](assets/")
        assert out.index("](assets/") < out.index("Between the figures.")
        assert out.index("Between the figures.") < out.rindex("](assets/")
        assert out.rindex("](assets/") < out.index("After the figure.")
        # The stub MarkItDown leaves behind must be fully consumed.
        assert "data:image" not in out

    def test_pptx_picture_is_saved_and_referenced(self, tmp_path: Path):
        from io import BytesIO

        from pptx import Presentation
        from pptx.util import Inches

        source = tmp_path / "deck.pptx"
        prs = Presentation()
        first = prs.slides.add_slide(prs.slide_layouts[5])
        first.shapes.title.text = "Deck"
        second = prs.slides.add_slide(prs.slide_layouts[5])
        second.shapes.title.text = "Architecture"
        second.shapes.add_picture(
            BytesIO(_png(480, 320)), Inches(1), Inches(2), Inches(4), Inches(2.6)
        )
        # A spacer that must leave nothing at all behind.
        second.shapes.add_picture(
            BytesIO(_png(6, 6, (0, 0, 0))),
            Inches(6),
            Inches(0.4),
            Inches(0.1),
            Inches(0.1),
        )
        prs.save(source)

        context = make_context(source, tmp_path)
        doc = convert_with_markitdown(context)
        out = context.markdown_output

        assert doc.stats.images == 1
        assert "](assets/" in out
        assert "[Image:" not in out
        # The figure belongs to slide 2, not slide 1.
        assert out.index("<!-- Slide number: 2 -->") < out.index("](assets/")
