"""Pytest configuration.

Environment variables are set before the app is imported so all storage
paths point at a temporary directory during tests.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_TMP = tempfile.mkdtemp(prefix="markforge-test-")

os.environ["MARKFORGE_STORAGE_DIR"] = os.path.join(_TMP, "storage")
os.environ["MARKFORGE_DATABASE_PATH"] = os.path.join(_TMP, "storage", "markforge.db")
os.environ["MARKFORGE_UPLOAD_DIR"] = os.path.join(_TMP, "storage", "uploads")
os.environ["MARKFORGE_OUTPUT_DIR"] = os.path.join(_TMP, "storage", "outputs")
os.environ["MARKFORGE_TEMP_DIR"] = os.path.join(_TMP, "storage", "temp")
os.environ["MARKFORGE_JOB_MODE"] = "sync"
os.environ["MARKFORGE_RETENTION_PERIOD"] = "1"
os.environ["MARKFORGE_JOB_TIMEOUT"] = "60"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import storage  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _bootstrap():
    init_db()
    storage.ensure_dirs()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def test_root() -> Path:
    return Path(_TMP)


def upload_pdf(client, name: str = "report.pdf") -> dict:
    """Upload a small text-based PDF and return the file record."""
    import pymupdf

    tmp = Path(_TMP) / name
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Introduction", fontsize=24)
    page.insert_text((72, 120), "This is a test paragraph for Markforge.")
    page.insert_text((72, 160), "Point one", fontsize=12)
    page.insert_text((72, 180), "Point two", fontsize=12)
    doc.save(tmp)
    doc.close()
    with open(tmp, "rb") as handle:
        response = client.post("/api/files/upload", files=[("files", (name, handle, "application/pdf"))])
    assert response.status_code == 200, response.text
    return response.json()[0]
