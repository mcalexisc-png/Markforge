"""Tests for the LAN access middleware (the cookie gate in app.main).

The auth endpoint and its rate limiter are covered in test_hardening.py;
these tests exercise the gate itself: which paths it protects, what it
accepts, and what it rejects.
"""

from __future__ import annotations

import pytest

from app.api.routes_auth import reset_rate_limits
from app.core.config import settings
from app.core.security import sign_token

_SECRET = "unit-test-secret-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _lan_on(monkeypatch):
    """LAN mode with a known password and a stable cookie secret."""
    monkeypatch.setattr(settings, "lan_mode", True)
    monkeypatch.setattr(settings, "lan_password", "correct-horse")
    monkeypatch.setattr(settings, "secret_key", _SECRET)
    reset_rate_limits()
    yield
    reset_rate_limits()


class TestLanGate:
    def test_public_paths_bypass_the_gate(self, client):
        assert client.get("/api/health").status_code == 200

    def test_verify_is_public(self, client):
        response = client.post("/api/auth/verify", json={"password": "correct-horse"})
        assert response.status_code == 200

    def test_protected_route_rejected_without_cookie(self, client):
        response = client.get("/api/jobs")
        assert response.status_code == 401
        assert response.json()["detail"] == "LAN access requires a password."

    def test_login_then_access(self, client):
        verify = client.post("/api/auth/verify", json={"password": "correct-horse"})
        assert verify.status_code == 200
        # The client keeps the issued cookie, so this request carries it.
        assert client.get("/api/jobs").status_code == 200

    def test_valid_signed_cookie_grants_access(self, client):
        token = sign_token(settings.cookie_secret(), {"lan": True})
        assert client.get("/api/jobs", cookies={"mf_access": token}).status_code == 200

    def test_tampered_signature_rejected(self, client):
        token = sign_token(settings.cookie_secret(), {"lan": True})
        forged = ("0" * 64) + token[64:]
        response = client.get("/api/jobs", cookies={"mf_access": forged})
        assert response.status_code == 401

    def test_expired_token_rejected(self, client):
        token = sign_token(settings.cookie_secret(), {"lan": True}, max_age=-1)
        response = client.get("/api/jobs", cookies={"mf_access": token})
        assert response.status_code == 401

    def test_token_from_another_install_rejected(self, client):
        token = sign_token("a-different-install-secret-0123456789", {"lan": True})
        response = client.get("/api/jobs", cookies={"mf_access": token})
        assert response.status_code == 401


class TestGateDisabled:
    def test_open_when_lan_mode_off(self, client, monkeypatch):
        monkeypatch.setattr(settings, "lan_mode", False)
        monkeypatch.setattr(settings, "lan_password", "correct-horse")
        assert client.get("/api/jobs").status_code == 200

    def test_open_when_no_password_configured(self, client, monkeypatch):
        # lan_mode alone must not lock the instance: main.py logs a warning
        # for this misconfiguration instead of bricking every request.
        monkeypatch.setattr(settings, "lan_password", "")
        assert client.get("/api/jobs").status_code == 200
