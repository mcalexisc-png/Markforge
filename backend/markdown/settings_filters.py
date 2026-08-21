"""Post-conversion settings filters for engine output.

The MarkItDown engine produces raw Markdown and cannot honor the app's
conversion settings itself. These filters rewrite its output so every toggle
in the settings panel has a visible effect, mirroring what the built-in
renderer does for the Common Document Model.

Applied in a fixed order so later filters see the effects of earlier ones:
1. boundary markers (clean mode / preserve_boundaries=off)
2. tables -> plain text (convert_tables=off)
3. links -> visible text (preserve_links=off)
4. whitespace normalization
"""

from __future__ import annotations

import re

from app.schemas.settings import ConversionSettings

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_SHEET_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|[\s:|-]+\|?\s*$")
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
_ASSET_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(assets/[^)]*\)")
_ESCAPED_PIPE_RE = re.compile(r"\\\|")


def _strip_comments(markdown: str) -> str:
    return _COMMENT_RE.sub("", markdown)


def _strip_sheet_headings(markdown: str) -> str:
    """Remove `## Sheet name` headings that directly precede a table."""
    lines = markdown.split("\n")
    out: list[str] = []
    for index, line in enumerate(lines):
        match = _SHEET_HEADING_RE.match(line)
        if match and _heading_precedes_table(lines, index):
            continue
        out.append(line)
    return "\n".join(out)


def _heading_precedes_table(lines: list[str], index: int) -> bool:
    """True when the next non-blank line after ``index`` starts a table."""
    for candidate in lines[index + 1 :]:
        if not candidate.strip():
            continue
        return bool(_TABLE_ROW_RE.match(candidate))
    return False


def _tables_to_text(markdown: str) -> str:
    """Replace Markdown table blocks with plain text lines of cell content."""
    lines = markdown.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not _TABLE_ROW_RE.match(line):
            out.append(line)
            index += 1
            continue

        block: list[str] = []
        while index < len(lines) and _TABLE_ROW_RE.match(lines[index]):
            block.append(lines[index])
            index += 1

        for row in block:
            if _TABLE_SEPARATOR_RE.match(row):
                continue
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            cells = [_ESCAPED_PIPE_RE.sub("|", cell) for cell in cells]
            cells = [re.sub(r"\s+", " ", cell) for cell in cells]
            out.append(" ".join(c for c in cells if c))
    return "\n".join(out)


def _strip_images(markdown: str) -> str:
    """Remove every image reference, extracted figures included."""
    return _IMAGE_RE.sub("", markdown)


def _links_to_text(markdown: str) -> str:
    """Flatten links to their text.

    Figures we extracted into ``assets/`` are deliberately preserved: turning
    off "preserve links" is about inline hyperlinks, and silently deleting the
    document's diagrams along with them loses content the user cannot recover.
    Remote images are still dropped -- fetching them would leave local-only.
    """
    stashed: dict[str, str] = {}

    def stash(match: re.Match[str]) -> str:
        key = f"\x00mfimg{len(stashed)}\x00"
        stashed[key] = match.group(0)
        return key

    text = _ASSET_IMAGE_RE.sub(stash, markdown)
    text = _IMAGE_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    for key, value in stashed.items():
        text = text.replace(key, value)
    return text


def apply_settings_filters(markdown: str, settings: ConversionSettings) -> str:
    """Rewrite ``markdown`` so it honors the user's conversion settings."""
    if settings.output_mode == "clean" or not settings.preserve_boundaries:
        markdown = _strip_comments(markdown)
        markdown = _strip_sheet_headings(markdown)
    if not settings.convert_tables:
        markdown = _tables_to_text(markdown)
    if not getattr(settings, "extract_images", True):
        markdown = _strip_images(markdown)
    if not settings.preserve_links:
        markdown = _links_to_text(markdown)
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip() + "\n"