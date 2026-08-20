"""Conversion engine support.

The app converts files exclusively with the MarkItDown engine. The adapter
lives in :mod:`converters.markitdown` with its custom PDF/PPTX converters and
shared PDF pre-pass helpers in :mod:`converters.pdf_helpers`.
"""

# File types accepted at upload (mirrors the formats MarkItDown is wired for).
ALLOWED_EXTENSIONS = (".pdf", ".docx", ".pptx", ".xlsx")