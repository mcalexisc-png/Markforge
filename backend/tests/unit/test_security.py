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
