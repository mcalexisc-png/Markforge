"""Programmatic fixture generation for tests.

Fixtures are generated on the fly (no binary files in the repo) so the
tests are self-contained and runnable offline.
"""

from __future__ import annotations

from pathlib import Path


def make_pdf(path: Path, *, pages: int = 3, scanned: bool = False) -> Path:
    import pymupdf

    doc = pymupdf.open()
    for index in range(1, pages + 1):
        page = doc.new_page()
        if not scanned:
            page.insert_text((72, 72), f"Chapter {index}", fontsize=24)
            page.insert_text((72, 120), f"Paragraph text on page {index}.", fontsize=12)
            page.insert_text((72, 160), "First point", fontsize=12)
            page.insert_text((72, 180), "Second point", fontsize=12)
            rect = pymupdf.Rect(72, 220, 250, 240)
            page.insert_text((72, 232), "https://example.com/page", fontsize=10)
            page.insert_link({"kind": pymupdf.LINK_URI, "from": rect, "uri": "https://example.com/page"})
    doc.set_metadata({"title": "Test Report", "author": "Markforge Tests"})
    doc.save(path)
    doc.close()
    return path


def make_scanned_pdf(path: Path, *, pages: int = 1) -> Path:
    """PDF with only images on the pages (no extractable text)."""
    from io import BytesIO

    import pymupdf
    from PIL import Image

    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        buffer = BytesIO()
        Image.new("RGB", (400, 500), color=(240, 240, 240)).save(buffer, format="PNG")
        buffer.seek(0)
        page.insert_image(page.rect, stream=buffer.read())
    doc.save(path)
    doc.close()
    return path


def _add_hyperlink(paragraph, url: str, text: str) -> None:
    """Insert a proper external hyperlink into a docx paragraph."""
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    part = paragraph.part
    r_id = part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def make_docx(path: Path) -> Path:
    from docx import Document

    doc = Document()
    doc.core_properties.title = "Sample Document"
    doc.core_properties.author = "Markforge Tests"
    doc.add_heading("Sample Document", level=0)
    doc.add_heading("Section One", level=1)
    doc.add_paragraph("A plain paragraph with some content.")
    p = doc.add_paragraph()
    run = p.add_run("Bold text and ")
    run.bold = True
    run2 = p.add_run("italic text")
    run2.italic = True
    p.add_run(" with a ")
    _add_hyperlink(p, "https://example.com", "link")
    doc.add_paragraph("First bullet", style="List Bullet")
    doc.add_paragraph("Second bullet", style="List Bullet")
    doc.add_paragraph("Numbered item", style="List Number")
    table = doc.add_table(rows=3, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).text = "Name"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Alpha"
    table.cell(1, 1).text = "10"
    table.cell(2, 0).text = "Beta"
    table.cell(2, 1).text = "20"
    doc.add_paragraph("A quote line", style="Intense Quote")
    doc.save(path)
    return path


def make_pptx(path: Path, *, slides: int = 3) -> Path:
    from pptx import Presentation

    titles = ["Introduction", "Network Architecture", "Deployment Plan"]
    prs = Presentation()
    for index in range(1, slides + 1):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        title = slide.shapes.title
        title.text = titles[index - 1]
        body = slide.placeholders[1]
        tf = body.text_frame
        tf.text = f"Content paragraph for slide {index}."
        tf.add_paragraph().text = "Bullet one"
        tf.add_paragraph().text = "Bullet two"
        notes = slide.notes_slide
        notes.notes_text_frame.text = f"Speaker notes for slide {index}."
    prs.save(path)
    return path


def make_xlsx(path: Path, *, sheets: int = 2) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Grades"
    ws.append(["Name", "Age", "Grade"])
    ws.append(["John", 20, "A"])
    ws.append(["Mary", 21, "B"])
    ws["A4"].hyperlink = "https://example.com/grade"
    ws.append(["", "22", "C"])
    ws.merge_cells("A5:B5")
    ws["A5"] = "Merged cell"
    from openpyxl.worksheet.table import Table, TableStyleInfo

    table = Table(displayName="GradesTable", ref="A1:C4")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
    ws.add_table(table)

    ws2 = wb.create_sheet("Notes")
    ws2.append(["Note"])
    ws2.append(["This sheet is for notes."])
    wb.save(path)
    return path


def make_two_column_pdf(path: Path) -> Path:
    """A PDF with a full-width header and two side-by-side columns."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 40), "Report header spanning both columns", fontsize=11)
    for index, line in enumerate(["Left column line A", "Left column line B", "Left column line C"]):
        page.insert_text((72, 80 + index * 22), line, fontsize=11)
    for index, line in enumerate(["Right column line A", "Right column line B", "Right column line C"]):
        page.insert_text((340, 80 + index * 22), line, fontsize=11)
    doc.save(path)
    doc.close()
    return path


def make_docx_reviewed(path: Path) -> Path:
    """DOCX with a review comment and tracked changes (insert/delete)."""

    from docx import Document
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    doc = Document()
    doc.add_heading("Reviewed Document", level=0)
    target = doc.add_paragraph("This paragraph carries a review comment.")

    comments_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:comment w:id="0" w:author="Reviewer" w:date="2026-08-16T10:00:00Z" w:initials="R">'
        "<w:p><w:r><w:t>Needs a citation.</w:t></w:r></w:p>"
        "</w:comment></w:comments>"
    )
    comments_part = Part(
        PackURI("/word/comments.xml"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
        comments_xml.encode("utf-8"),
        doc.part.package,
    )
    doc.part.relate_to(
        comments_part,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
    )

    start = OxmlElement("w:commentRangeStart")
    start.set(qn("w:id"), "0")
    end = OxmlElement("w:commentRangeEnd")
    end.set(qn("w:id"), "0")
    ref_run = OxmlElement("w:r")
    ref_rpr = OxmlElement("w:rPr")
    ref_el = OxmlElement("w:commentReference")
    ref_el.set(qn("w:id"), "0")
    ref_rpr.append(ref_el)
    ref_run.append(ref_rpr)
    p_el = target._p
    p_el.append(start)
    p_el.append(end)
    p_el.append(ref_run)

    tracked = doc.add_paragraph()
    ins = OxmlElement("w:ins")
    ins.set(qn("w:id"), "1")
    ins.set(qn("w:author"), "Author")
    ins_run = OxmlElement("w:r")
    ins_t = OxmlElement("w:t")
    ins_t.text = "Inserted sentence"
    ins_run.append(ins_t)
    ins.append(ins_run)
    tracked._p.append(ins)

    dele = OxmlElement("w:del")
    dele.set(qn("w:id"), "2")
    dele.set(qn("w:author"), "Author")
    del_run = OxmlElement("w:r")
    del_text = OxmlElement("w:delText")
    del_text.text = "Removed sentence"
    del_run.append(del_text)
    dele.append(del_run)
    tracked._p.append(dele)

    doc.save(path)
    return path


def make_pptx_charts(path: Path, *, slides: int = 2) -> Path:
    """PPTX with a column chart and speaker notes on every slide."""
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE

    prs = Presentation()
    for index in range(1, slides + 1):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = f"Quarterly Results {index}"
        body = slide.placeholders[1]
        body.text_frame.text = "Summary of quarterly performance."

        chart_data = CategoryChartData()
        chart_data.categories = ["Q1", "Q2", "Q3"]
        chart_data.add_series("Revenue", (100 + index, 150 + index, 200 + index))
        chart_data.add_series("Costs", (60 + index, 90 + index, 120 + index))
        slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            2 * 914400,
            1 * 914400,
            4 * 914400,
            3 * 914400,
            chart_data,
        )

        slide.notes_slide.notes_text_frame.text = f"Speaker notes for slide {index}."
    prs.save(path)
    return path


def make_xlsx_charts(path: Path) -> Path:
    """XLSX with a chart and a cell comment."""
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.comments import Comment

    wb = Workbook()
    ws = wb.active
    ws.title = "Quarterly"
    ws.append(["Quarter", "Revenue", "Costs"])
    ws.append(["Q1", 100, 60])
    ws.append(["Q2", 150, 90])
    ws.append(["Q3", 200, 120])
    ws["A2"].comment = Comment("Starts below expectations.", "Analyst")

    chart = BarChart()
    chart.title = "Revenue vs costs"
    data = Reference(ws, min_col=2, max_col=3, min_row=1, max_row=4)
    cats = Reference(ws, min_col=1, min_row=2, max_row=4)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    ws.add_chart(chart, "F2")

    wb.save(path)
    return path


def make_text_pdf_with_image(path: Path) -> Path:
    """PDF containing an embedded image (used for asset extraction tests)."""
    from io import BytesIO

    import pymupdf
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (64, 64), color=(200, 30, 30)).save(buffer, format="PNG")
    buffer.seek(0)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=buffer.read())
    page.insert_text((72, 72), "Image page", fontsize=18)
    doc.save(path)
    doc.close()
    return path
