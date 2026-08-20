"""Tests for the per-install secret key and the LAN auth rate limiter."""

from __future__ import annotations

import pytest

from app.api import routes_auth
from app.api.routes_auth import reset_rate_limits
from app.core.config import settings
from app.core.security import verify_token


class TestSecretKey:
    def test_custom_key_used_as_is(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "secret_key", "my-custom-key-0123456789abcdef")
        monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
        assert settings.cookie_secret() == "my-custom-key-0123456789abcdef"

    def test_placeholder_keys_are_ignored(self, tmp_path, monkeypatch):
        for placeholder in ("change-me", "change_me", "changeme", "dev-only-change-me"):
            monkeypatch.setattr(settings, "secret_key", placeholder)
            monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
            secret = settings.cookie_secret()
            assert secret != placeholder
            assert len(secret) >= 32

    def test_short_keys_are_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "secret_key", "short")
        monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
        assert len(settings.cookie_secret()) >= 32

    def test_default_key_generates_and_persists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "secret_key", "dev-only-change-me")
        monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
        monkeypatch.setattr(settings, "lan_password", "")

        first = settings.cookie_secret()
        assert len(first) >= 32
        assert first != "dev-only-change-me"

        second = settings.cookie_secret()
        assert second == first, "the generated key must be stable across calls"

        key_file = tmp_path / "storage" / ".secret_key"
        assert key_file.exists()
        assert key_file.read_text(encoding="utf-8").strip() == first

    def test_generated_key_signs_and_verifies(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "secret_key", "dev-only-change-me")
        monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
        secret = settings.cookie_secret()
        token = __import__("app.core.security", fromlist=["sign_token"]).sign_token(
            secret, {"lan": True}
        )
        assert verify_token(secret, token)
        assert not verify_token("a-different-secret", token)


class TestRateLimit:
    def test_wrong_password_rejected(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "lan_mode", True)
        monkeypatch.setattr(settings, "lan_password", "correct-horse")
        reset_rate_limits()
        response = client.post("/api/auth/verify", json={"password": "wrong"})
        assert response.status_code == 401

    def test_correct_password_accepted(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "lan_mode", True)
        monkeypatch.setattr(settings, "lan_password", "correct-horse")
        reset_rate_limits()
        response = client.post("/api/auth/verify", json={"password": "correct-horse"})
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert "mf_access" in response.cookies

    def test_brute_force_throttled(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "lan_mode", True)
        monkeypatch.setattr(settings, "lan_password", "correct-horse")
        reset_rate_limits()
        for _ in range(routes_auth.MAX_ATTEMPTS):
            assert client.post("/api/auth/verify", json={"password": "nope"}).status_code == 401
        throttled = client.post("/api/auth/verify", json={"password": "correct-horse"})
        assert throttled.status_code == 429
        assert "Retry-After" in throttled.headers
        reset_rate_limits()

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        yield
        reset_rate_limits()
