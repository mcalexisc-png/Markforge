"""Conversion result model.

The converters emit Markdown text directly; this package carries the metadata,
statistics and warnings that accompany it.
"""

from __future__ import annotations

from document_model.document import ConversionWarning, Document, DocumentStats
from document_model.metadata import normalize_metadata

__all__ = [
    "ConversionWarning",
    "Document",
    "DocumentStats",
    "normalize_metadata",
]
