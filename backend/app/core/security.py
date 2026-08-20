"""Security helpers: constant-time password checks and safe filenames."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from pathlib import Path
from typing import Any

_UNSAFE_NAME_RE = re.compile(r"[^\w. ()-]+", re.UNICODE)


def safe_filename(name: str, max_length: int = 120) -> str:
    """Sanitize an uploaded filename to prevent path traversal and oddities."""
    name = name.replace("\\", "/")  # normalize separators on every OS
    name = Path(name).name
    name = name.replace("\x00", "")
    name = _UNSAFE_NAME_RE.sub("_", name).strip(" .")
    if not name:
        name = "document"
    if len(name) > max_length:
        stem, ext = Path(name).stem, Path(name).suffix
        budget = max_length - len(ext)
        keep = max(1, budget - 9)
        name = f"{stem[:keep]}_{secrets.token_hex(4)}{ext}"
        if len(name) > max_length:
            name = name[:max_length]
    return name


def safe_stem(name: str, max_length: int = 80) -> str:
    """Filename-safe stem used for output directories and downloads."""
    return safe_filename(name, max_length=max_length).rsplit(".", 1)[0]


def secure_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8", errors="ignore"), b.encode("utf-8", errors="ignore"))


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sign_token(secret: str, payload: dict[str, Any], max_age: int = 12 * 3600) -> str:
    """HMAC-signed JSON token for the LAN access cookie."""
    import json
    import time

    token_payload = {**payload, "exp": int(time.time()) + max_age}
    raw = json.dumps(token_payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return f"{sig}.{raw.decode()}"


def verify_token(secret: str, token: str | None, now: int | None = None) -> bool:
    """Verify and return True when the token is valid and unexpired."""
    import json
    import time

    if not token or "." not in token:
        return False
    sig, raw = token.split(".", 1)
    expected = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        payload = json.loads(raw)
    except ValueError:
        return False
    if now is None:
        now = int(time.time())
    return bool(payload.get("exp") and int(payload["exp"]) > now)
