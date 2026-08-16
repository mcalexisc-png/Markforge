"""Health checks: API, Redis, worker, storage."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.job import HealthOut
from app.services.storage import storage_status

router = APIRouter(prefix="/api/health", tags=["health"])


def _redis_health() -> str:
    if settings.job_mode != "celery":
        return "disabled (sync mode)"
    try:
        import redis

        client = redis.from_url(settings.redis_url, socket_timeout=2)
        return "healthy" if client.ping() else "unreachable"
    except Exception:
        return "unreachable"


def _worker_health() -> str:
    if settings.job_mode != "celery":
        return "disabled (sync mode)"
    try:
        import redis

        client = redis.from_url(settings.redis_url, socket_timeout=2)
        keys = client.keys("celery@*")
        return "healthy" if keys else "no worker connected"
    except Exception:
        return "unreachable"


@router.get("", response_model=HealthOut)
async def health() -> HealthOut:
    storage = storage_status()
    return HealthOut(
        status="ok",
        redis=_redis_health(),
        worker=_worker_health(),
        storage="writable" if storage["writable"] else "read-only",
        lan={
            "enabled": settings.lan_mode,
            "auth_required": bool(settings.lan_mode and settings.lan_password),
        },
    )
