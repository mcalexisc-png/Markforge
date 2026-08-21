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


class TestAllowedFormatsHaveTheirDependencies:
    """Every allowed extension must have its MarkItDown extra installed.

    MarkItDown raises MissingDependencyException from inside convert(), so an
    extension added to ALLOWED_EXTENSIONS without its extra in requirements.txt
    passes upload validation and then fails *every* conversion at runtime.
    This is how `.xls` shipped broken: the allowlist and the registered
    converter were both updated, but `markitdown[xls]` was not installed.
    """

    # A byte stub per family, just enough to reach the converter's dependency
    # check. Parse errors are fine and expected; missing dependencies are not.
    _OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512
    _ZIP = b"PK\x03\x04" + b"\x00" * 64
    _STUBS = {
        ".pdf": b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\ntrailer<<>>\n%%EOF\n",
        ".docx": _ZIP,
        ".pptx": _ZIP,
        ".xlsx": _ZIP,
        ".xls": _OLE2,
        ".msg": _OLE2,
        ".epub": _ZIP,
        ".csv": b"a,b\n1,2\n",
        ".tsv": b"a\tb\n1\t2\n",
        ".html": b"<html><body><p>x</p></body></html>",
        ".htm": b"<html><body><p>x</p></body></html>",
        ".txt": b"plain text\n",
        ".md": b"# heading\n",
        ".json": b'{"a": 1}',
        ".xml": b"<?xml version='1.0'?><r><i>x</i></r>",
        ".ipynb": b'{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}',
    }

    def test_every_allowed_extension_has_its_dependency_installed(self, tmp_path):
        from app.schemas.settings import ConversionSettings
        from converters import ALLOWED_EXTENSIONS
        from converters.base import ConversionContext, ConversionError
        from converters.markitdown import convert_with_markitdown

        missing_stub = [e for e in ALLOWED_EXTENSIONS if e not in self._STUBS]
        assert not missing_stub, f"add a stub for {missing_stub} so it is covered"

        broken: list[str] = []
        for extension in ALLOWED_EXTENSIONS:
            source = tmp_path / f"sample{extension}"
            source.write_bytes(self._STUBS[extension])
            output = tmp_path / f"out{extension.lstrip('.')}"
            output.mkdir(exist_ok=True)
            context = ConversionContext(
                source_path=source,
                settings=ConversionSettings(),
                output_dir=output,
            )
            try:
                convert_with_markitdown(context)
            except ConversionError as exc:
                # A malformed stub failing to parse is expected. A converter
                # reporting that its dependency is absent is not.
                if "MissingDependencyException" in (exc.detail or ""):
                    broken.append(extension)
            except Exception:  # noqa: BLE001 - any other failure is a parse issue
                pass

        assert not broken, (
            f"these allowed formats have no working converter: {broken}. "
            "Add the matching MarkItDown extra to backend/requirements.txt."
        )
