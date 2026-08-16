"""Normalized source metadata (title, author, dates, producer, ...)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

_KEYS = {
    "title": "title",
    "author": "author",
    "subject": "subject",
    "keywords": "keywords",
    "creator": "creator",
    "producer": "producer",
    "creation_date": "created_at",
    "modification_date": "modified_at",
    "creationtime": "created_at",
    "modificationtime": "modified_at",
}

_SKIP = {"format", "encryption", "scheme"}


def _to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # PyMuPDF-style dates: D:20240101120000+02'00'
    if text.startswith("D:"):
        text = text[2:]
        text = text.replace("'", "").replace("Z", "")
        for fmt in (
            "%Y%m%d%H%M%S%z",
            "%Y%m%d%H%M%S",
            "%Y%m%d%H%M",
            "%Y%m%d",
        ):
            try:
                return datetime.strptime(text[: len(fmt)], fmt).isoformat()
            except ValueError:
                continue
    return text


def normalize_metadata(raw: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in raw.items():
        if value is None or key in _SKIP:
            continue
        normalized_key = _KEYS.get(key.lower(), key.lower())
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value)
        if isinstance(value, bool):
            value = "true" if value else "false"
        if isinstance(value, (int, float)):
            value = str(value)
        iso = _to_iso(value)
        if iso is not None:
            out[normalized_key] = iso
    return out
