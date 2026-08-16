"""Markforge backend entry point.

Run locally (no Redis required):
    uvicorn app.main:app --host 127.0.0.1 --port 3001
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_auth, routes_files, routes_health, routes_jobs, routes_settings
from app.core.config import settings
from app.core.db import SessionLocal, init_db
from app.core.logging import configure_logging
from app.core.security import verify_token
from app.models.job import RetentionLog
from app.services import storage

logger = logging.getLogger("markforge.app")

_PUBLIC_PATHS = {"/api/health", "/api/auth/verify"}


async def _cleanup_loop() -> None:
    while True:
        try:
            deleted, freed = storage.run_retention()
            temp_removed = storage.cleanup_temp()
            if deleted or temp_removed:
                logger.info(
                    "Retention cleanup: %d old outputs (%d MB), %d temp dirs",
                    deleted,
                    freed // (1024 * 1024),
                    temp_removed,
                )
            db = SessionLocal()
            try:
                db.add(
                    RetentionLog(deleted_jobs=deleted, freed_bytes=freed)
                )
                db.commit()
            finally:
                db.close()
        except Exception:
            logger.exception("Retention cleanup failed")
        await asyncio.sleep(max(60, settings.cleanup_interval))


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    init_db()
    storage.ensure_dirs()
    task = asyncio.create_task(_cleanup_loop())
    if settings.lan_mode:
        if not settings.lan_password:
            logger.warning(
                "LAN mode is enabled but MARKFORGE_LAN_PASSWORD is empty: "
                "the instance is open to anyone on the network."
            )
        if settings.secret_is_default:
            logger.warning(
                "MARKFORGE_SECRET_KEY is unset; a per-install key was generated "
                "and stored in the data directory. Set it explicitly to keep it "
                "stable across moves or backups."
            )
    logger.info(
        "Markforge backend ready (env=%s, host=%s, lan=%s, job_mode=%s)",
        settings.app_env,
        settings.host,
        settings.lan_mode,
        settings.job_mode,
    )
    yield
    task.cancel()


app = FastAPI(
    title="Markforge API",
    description="Local-first document to Markdown conversion",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def lan_access_middleware(request: Request, call_next):
    """Optional LAN password protection for everything but health/auth."""
    path = request.url.path
    if settings.lan_mode and settings.lan_password and path not in _PUBLIC_PATHS:
        token = request.cookies.get("mf_access")
        if not verify_token(settings.cookie_secret(), token):
            return JSONResponse(
                status_code=401,
                content={"detail": "LAN access requires a password."},
            )
    return await call_next(request)


app.include_router(routes_files.router)
app.include_router(routes_jobs.router)
app.include_router(routes_settings.router)
app.include_router(routes_auth.router)
app.include_router(routes_health.router)


@app.get("/")
async def root() -> dict:
    return {"name": "Markforge API", "version": "1.0.0", "docs": "/docs"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return Response(status_code=500, content="Internal server error")
