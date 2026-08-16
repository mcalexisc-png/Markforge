"""LAN access password verification (simple, no accounts).

The verify endpoint is throttled per client IP to discourage brute force
attempts. The throttle is in-process (fine for the single-instance sync
deployment this app targets).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import settings
from app.core.security import secure_compare, sign_token
from app.schemas.job import VerifyIn

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60.0
_attempts: dict[str, deque] = defaultdict(deque)


def reset_rate_limits() -> None:
    """Clear the in-memory attempt log (used by tests)."""
    _attempts.clear()


def _rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    window = _attempts[client_ip]
    while window and now - window[0] > WINDOW_SECONDS:
        window.popleft()
    if len(window) >= MAX_ATTEMPTS:
        return True
    window.append(now)
    return False


@router.post("/verify")
async def verify(payload: VerifyIn, request: Request, response: Response) -> dict:
    if not settings.lan_password:
        return {"ok": True, "enabled": False}

    client_ip = request.client.host if request.client else "unknown"
    if _rate_limited(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Try again in a minute.",
            headers={"Retry-After": str(int(WINDOW_SECONDS))},
        )

    if not secure_compare(payload.password, settings.lan_password):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    token = sign_token(settings.cookie_secret(), {"lan": True})
    response.set_cookie(
        key="mf_access",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=12 * 3600,
        path="/",
    )
    return {"ok": True, "enabled": True}
