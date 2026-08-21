"""Conversion engine support.

The app converts files exclusively with the MarkItDown engine. The adapter
lives in :mod:`converters.markitdown` with its custom PDF/PPTX converters and
shared PDF pre-pass helpers in :mod:`converters.pdf_helpers`.
"""

# File types accepted at upload.
#
# Every entry must be convertible by a converter registered in
# ``converters.markitdown.build_local_engine`` -- which registers local
# converters only. Formats MarkItDown handles through a network service are
# deliberately absent and must stay that way:
#
#   audio (.mp3/.wav/.m4a)  transcribed by uploading to Google's Web Speech API
#   images (.jpg/.png/...)  only meaningful with a remote LLM caption client
#   .zip                    recursively converts members, so it could reach a
#                           converter the allowlist would otherwise exclude
#
# ``TestEngineIsLocalOnly`` in tests/unit/test_security.py guards the pairing.
ALLOWED_EXTENSIONS = (
    # Documents
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".epub",
    ".msg",
    # Data / text
    ".csv",
    ".tsv",
    ".html",
    ".htm",
    ".txt",
    ".md",
    ".json",
    ".xml",
    ".ipynb",
)
