"""Post-render cleanup: whitespace normalization and final polish.

The renderer produces the structure; cleanup makes the output consistently
readable, valid and stable regardless of source quirks.
"""

from __future__ import annotations

import re


def normalize_whitespace(markdown: str) -> str:
    """Collapse runaway blank lines, trim trailing spaces per line."""
    lines = markdown.split("\n")
    cleaned = [line.rstrip() for line in lines]
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def ensure_final_newline(markdown: str) -> str:
    markdown = markdown.rstrip("\n")
    return markdown + "\n"


def strip_page_artifacts(markdown: str) -> str:
    """Remove `## Page N` / `# Slide N` headings and leading rules.

    Used by the clean output mode when boundary headings leak through.
    """
    text = re.sub(r"^## Page \d+\s*$", "", markdown, flags=re.MULTILINE)
    text = re.sub(r"^# Slide \d+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?^\s*---\s*$\n?", "\n", text, flags=re.MULTILINE)
    return normalize_whitespace(text)


def postprocess(markdown: str, *, output_mode: str = "fidelity") -> str:
    text = normalize_whitespace(markdown)
    if output_mode == "clean":
        text = strip_page_artifacts(text)
    return ensure_final_newline(text)
