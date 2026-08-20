"""Unit tests for the MarkItDown output settings filters."""

from __future__ import annotations

from app.schemas.settings import ConversionSettings
from markdown.settings_filters import apply_settings_filters

SAMPLE = """<!-- Slide number: 1 -->

# Title

| Name | Age |
| --- | --- |
| Ana | 30 |
| Ben | 25 |

See [our site](https://example.com) for details.
"""


def _settings(**overrides) -> ConversionSettings:
    return ConversionSettings(**overrides)


class TestBoundaryFilters:
    def test_comments_kept_in_fidelity(self):
        out = apply_settings_filters(SAMPLE, _settings(output_mode="fidelity"))
        assert "<!-- Slide number: 1 -->" in out

    def test_comments_stripped_in_clean(self):
        out = apply_settings_filters(SAMPLE, _settings(output_mode="clean"))
        assert "<!--" not in out

    def test_comments_stripped_when_boundaries_off(self):
        out = apply_settings_filters(SAMPLE, _settings(preserve_boundaries=False))
        assert "<!--" not in out

    def test_sheet_headings_preceding_tables_stripped_in_clean(self):
        markdown = "## Sales\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n## Conclusion\n\nSome text.\n"
        out = apply_settings_filters(markdown, _settings(output_mode="clean"))
        assert "## Sales" not in out
        assert "## Conclusion" in out


class TestTableFilter:
    def test_tables_to_text(self):
        out = apply_settings_filters(SAMPLE, _settings(convert_tables=False))
        assert "|" not in out
        assert "Ana 30" in out
        assert "Ben 25" in out
        assert "Name Age" in out

    def test_tables_kept_when_enabled(self):
        out = apply_settings_filters(SAMPLE, _settings(convert_tables=True))
        assert "| Name | Age |" in out


class TestLinkFilter:
    def test_links_to_text(self):
        out = apply_settings_filters(SAMPLE, _settings(preserve_links=False))
        assert "](https://example.com)" not in out
        assert "our site" in out

    def test_links_kept_when_enabled(self):
        out = apply_settings_filters(SAMPLE, _settings(preserve_links=True))
        assert "[our site](https://example.com)" in out


class TestCombinations:
    def test_all_off(self):
        out = apply_settings_filters(
            SAMPLE,
            _settings(output_mode="clean", convert_tables=False, preserve_links=False),
        )
        assert "<!--" not in out
        assert "|" not in out
        assert "](https://example.com)" not in out
        assert out.endswith("\n")
        assert "\n\n\n" not in out