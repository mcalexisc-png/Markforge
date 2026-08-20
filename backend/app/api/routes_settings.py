"""Persisted user settings (output mode, OCR, toggles)."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.core.db import SessionLocal
from app.models.job import AppSetting
from app.schemas.settings import DEFAULT_SETTINGS, UserSettings

logger = logging.getLogger("markforge.settings")

router = APIRouter(prefix="/api/settings", tags=["settings"])

_KEY = "user_settings"


def get_persisted() -> UserSettings:
    db = SessionLocal()
    try:
        row = db.get(AppSetting, _KEY)
        if row is None or not row.value:
            return DEFAULT_SETTINGS.model_copy()
        try:
            return UserSettings.model_validate_json(row.value)
        except ValueError:
            logger.warning("Persisted settings are corrupt; using defaults")
            return DEFAULT_SETTINGS.model_copy()
    finally:
        db.close()


@router.get("", response_model=UserSettings)
async def get_settings() -> UserSettings:
    return get_persisted()


@router.put("", response_model=UserSettings)
async def put_settings(settings: UserSettings) -> UserSettings:
    db = SessionLocal()
    try:
        row = db.get(AppSetting, _KEY)
        if row is None:
            row = AppSetting(key=_KEY, value="")
            db.add(row)
        row.value = settings.model_dump_json()
        db.commit()
    finally:
        db.close()
    return settings
