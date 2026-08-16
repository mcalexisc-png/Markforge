"""Unit tests for the Markdown renderer."""

from __future__ import annotations

from document_model import (
    BulletListBlock,
    CaptionBlock,
    CodeBlock,
    Document,
    FootnoteBlock,
    HeadingBlock,
    HorizontalRuleBlock,
    ImageBlock,
    LinkBlock,
    NumberedListBlock,
    PageBreakBlock,
    ParagraphBlock,
    QuoteBlock,
    SlideBreakBlock,
    TableBlock,
    TableCell,
    TableRow,
    TextRun,
)
from markdown.renderer import render_document


def make_doc(*blocks) -> Document:
    return Document(format="test", filename="t.md", blocks=list(blocks))


class TestHeadings:
    def test_levels(self):
        out = render_document(make_doc(HeadingBlock(level=1, content=[TextRun(text="One")])))
        assert out.startswith("# One")
        out = render_document(make_doc(HeadingBlock(level=3, content=[TextRun(text="Three")])))
        assert out.startswith("### Three")

    def test_heading_escapes_hash(self):
        out = render_document(make_doc(HeadingBlock(level=1, content=[TextRun(text="C# Notes")])))
        assert "C\\# Notes" in out


class TestEmphasis:
    def test_bold_italic(self):
        out = render_document(
            make_doc(ParagraphBlock(content=[TextRun(text="word", bold=True)]))
        )
        assert "**word**" in out
        out = render_document(
            make_doc(ParagraphBlock(content=[TextRun(text="word", italic=True)]))
        )
        assert "*word*" in out

    def test_escapes_underscores(self):
        out = render_document(make_doc(ParagraphBlock(content=[TextRun(text="a_b_c")])))
        assert "a\\_b\\_c" in out


class TestLists:
    def test_bullets(self):
        out = render_document(
            make_doc(
                BulletListBlock(
                    items=[
                        [TextRun(text="one")],
                        [TextRun(text="two", bold=True)],
                    ]
                )
            )
        )
        assert out == "- one\n- **two**\n"

    def test_numbered(self):
        out = render_document(
            make_doc(NumberedListBlock(items=[[TextRun(text="a")], [TextRun(text="b")]], start=3))
        )
        assert out == "3. a\n4. b\n"


class TestTables:
    def test_header_and_alignment(self):
        table = TableBlock(
            has_header=True,
            rows=[
                TableRow(
                    cells=[
                        TableCell(content=[TextRun(text="Name")]),
                        TableCell(content=[TextRun(text="Age")]),
                    ]
                ),
                TableRow(
                    cells=[
                        TableCell(content=[TextRun(text="John")]),
                        TableCell(content=[TextRun(text="20")], align="right"),
                    ]
                ),
            ],
        )
        out = render_document(make_doc(table))
        assert "| Name | Age |" in out
        assert "| --- | ---: |" in out
        assert "| John | 20 |" in out

    def test_pipe_escaped(self):
        table = TableBlock(
            has_header=False,
            rows=[
                TableRow(cells=[TableCell(content=[TextRun(text="a|b")])]),
            ],
        )
        out = render_document(make_doc(table))
        assert "a\\|b" in out

    def test_multiline_cell_uses_br(self):
        table = TableBlock(
            has_header=False,
            rows=[
                TableRow(cells=[TableCell(content=[TextRun(text="line1\nline2")])]),
            ],
        )
        out = render_document(make_doc(table))
        assert "line1<br>line2" in out

    def test_empty_cells_preserved(self):
        table = TableBlock(
            has_header=False,
            rows=[
                TableRow(cells=[TableCell(content=[]), TableCell(content=[TextRun(text="x")])]),
            ],
        )
        out = render_document(make_doc(table))
        assert "|  | x |" in out

    def test_uneven_rows_padded(self):
        table = TableBlock(
            has_header=False,
            rows=[
                TableRow(cells=[TableCell(content=[TextRun(text="a")])]),
                TableRow(
                    cells=[
                        TableCell(content=[TextRun(text="b")]),
                        TableCell(content=[TextRun(text="c")]),
                    ]
                ),
            ],
        )
        out = render_document(make_doc(table))
        assert "| a |  |" in out
        assert "| b | c |" in out


class TestLinksAndImages:
    def test_link(self):
        out = render_document(
            make_doc(LinkBlock(href="https://example.com", content=[TextRun(text="site")]))
        )
        assert "[site](https://example.com)" in out

    def test_link_with_style(self):
        out = render_document(
            make_doc(ParagraphBlock(content=[TextRun(text="click", href="https://x.dev")]))
        )
        assert "[click](https://x.dev)" in out

    def test_image(self):
        out = render_document(
            make_doc(ImageBlock(path="assets/image-001.png", alt="Figure 1"))
        )
        assert "![Figure 1](assets/image-001.png)" in out

    def test_image_with_caption(self):
        out = render_document(
            make_doc(
                ImageBlock(path="assets/1.png", alt="x", caption="A caption")
            )
        )
        assert "*A caption*" in out


class TestBlocks:
    def test_code(self):
        out = render_document(
            make_doc(CodeBlock(language="python", code="print('hi')"))
        )
        assert "```python\nprint('hi')\n```" in out

    def test_quote(self):
        out = render_document(
            make_doc(QuoteBlock(content=[TextRun(text="beep"), TextRun(text="boop")]))
        )
        assert "> beep" in out
        assert "> boop" in out

    def test_caption(self):
        out = render_document(make_doc(CaptionBlock(content=[TextRun(text="Fig. 1")])))
        assert "*Fig. 1*" in out

    def test_footnote(self):
        out = render_document(
            make_doc(
                ParagraphBlock(content=[TextRun(text="text"), TextRun(text="note", code=True)]),
                FootnoteBlock(number=1, content=[TextRun(text="A note")]),
            )
        )
        assert "[^1]: A note" in out


class TestBoundaries:
    def test_fidelity_keeps_page_breaks(self):
        doc = make_doc(
            PageBreakBlock(page_number=1),
            ParagraphBlock(content=[TextRun(text="p1")]),
            PageBreakBlock(page_number=2),
            ParagraphBlock(content=[TextRun(text="p2")]),
        )
        out = render_document(doc, output_mode="fidelity")
        assert "## Page 1" in out
        assert "## Page 2" in out
        assert "---" in out

    def test_clean_drops_page_breaks(self):
        doc = make_doc(
            PageBreakBlock(page_number=1),
            ParagraphBlock(content=[TextRun(text="p1")]),
            PageBreakBlock(page_number=2),
            ParagraphBlock(content=[TextRun(text="p2")]),
        )
        out = render_document(doc, output_mode="clean")
        assert "## Page" not in out
        assert "---" not in out
        assert out.strip() == "p1\n\np2"

    def test_slide_breaks(self):
        doc = make_doc(
            SlideBreakBlock(slide_number=1),
            HeadingBlock(level=1, content=[TextRun(text="Intro")]),
            SlideBreakBlock(slide_number=2),
            HeadingBlock(level=1, content=[TextRun(text="Arch")]),
        )
        out = render_document(doc, output_mode="fidelity")
        assert "# Slide 1" in out
        assert "# Slide 2" in out

    def test_preserve_boundaries_false(self):
        doc = make_doc(
            PageBreakBlock(page_number=1),
            ParagraphBlock(content=[TextRun(text="p1")]),
        )
        out = render_document(doc, preserve_boundaries=False)
        assert "---" not in out
        assert "p1" in out

    def test_horizontal_rule(self):
        out = render_document(make_doc(HorizontalRuleBlock()))
        assert out.strip() == "---"


class TestNormalization:
    def test_whitespace_collapsed(self):
        doc = make_doc(
            ParagraphBlock(content=[TextRun(text="one")]),
            ParagraphBlock(content=[TextRun(text="two")]),
            ParagraphBlock(content=[TextRun(text="three")]),
        )
        out = render_document(doc)
        assert out == "one\n\ntwo\n\nthree\n"

    def test_trailing_spaces_trimmed(self):
        doc = make_doc(ParagraphBlock(content=[TextRun(text="hi  ") ]))
        out = render_document(doc)
        assert out == "hi\n"

    def test_multiline_paragraph_split(self):
        doc = make_doc(ParagraphBlock(content=[TextRun(text="line1\nline2")]))
        out = render_document(doc)
        assert "line1\n\nline2" in out
