"""Unit tests for filename sanitization and token signing."""

from __future__ import annotations

from app.core.security import (
    safe_filename,
    safe_stem,
    secure_compare,
    sha256_of_bytes,
    sign_token,
    verify_token,
)


class TestSafeFilename:
    def test_basename_only(self):
        assert safe_filename("../../etc/passwd") == "passwd"

    def test_path_traversal_with_backslash(self):
        assert ".." not in safe_filename(r"..\..\evil.docx")

    def test_special_chars_removed(self):
        assert safe_filename("my <doc> | final?.pdf") == "my _doc_ _ final_.pdf"

    def test_empty_falls_back(self):
        assert safe_filename("") == "document"

    def test_dots_only_falls_back(self):
        assert safe_filename("....") == "document"

    def test_long_name_truncated(self):
        name = "x" * 300 + ".pdf"
        result = safe_filename(name, max_length=120)
        assert len(result) <= 120
        assert result.endswith(".pdf")

    def test_unicode_kept(self):
        assert safe_filename("café notes.pdf") == "café notes.pdf"


class TestSafeStem:
    def test_stem(self):
        assert safe_stem("report.final.pdf") == "report.final"

    def test_no_extension(self):
        assert safe_stem("notes") == "notes"


class TestHashing:
    def test_sha256(self):
        assert sha256_of_bytes(b"hello") == (
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )


class TestTokens:
    def test_roundtrip(self):
        token = sign_token("secret", {"lan": True})
        assert verify_token("secret", token)

    def test_wrong_secret(self):
        token = sign_token("secret", {"lan": True})
        assert not verify_token("other", token)

    def test_expired(self):
        token = sign_token("secret", {"lan": True}, max_age=0)
        assert not verify_token("secret", token)

    def test_garbage(self):
        assert not verify_token("secret", None)
        assert not verify_token("secret", "garbage.token")

    def test_secure_compare(self):
        assert secure_compare("abc", "abc")
        assert not secure_compare("abc", "abd")


class TestEngineIsLocalOnly:
    """The conversion engine must never register a converter that egresses.

    MarkItDown's default ``enable_builtins()`` registers an audio converter
    that uploads audio to Google's Web Speech API, several URL fetchers, and
    two Azure cloud converters. ``build_local_engine`` opts out of builtins
    entirely and adds back only local converters, so an unsupported format --
    or one nested inside an archive -- has no converter to land on.
    """

    def test_no_network_converter_is_registered(self):
        from converters.markitdown import NETWORK_CONVERTER_NAMES, build_local_engine

        engine = build_local_engine()
        registered = {type(r.converter).__name__ for r in engine._converters}
        assert not (registered & NETWORK_CONVERTER_NAMES)

    def test_builtins_are_not_enabled(self):
        from converters.markitdown import build_local_engine

        assert build_local_engine()._builtins_enabled is False

    def test_custom_converters_outrank_stock_ones(self):
        """Ours are registered last, so they are tried first."""
        from converters.markitdown import build_local_engine

        names = [type(r.converter).__name__ for r in build_local_engine()._converters]
        assert names.index("ColumnAwarePdfConverter") < names.index("PdfConverter")
        assert names.index("HeadingPptxConverter") < names.index("PptxConverter")
