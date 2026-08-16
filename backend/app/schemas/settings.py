"""Pydantic schemas shared between the API and conversion workers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ConversionSettings(BaseModel):
    """Conversion options chosen by the user before a job starts."""

    output_mode: Literal["fidelity", "clean"] = "fidelity"
    ocr_mode: Literal["auto", "always", "never"] = "auto"
    preserve_boundaries: bool = True
    extract_images: bool = True
    convert_tables: bool = True
    preserve_links: bool = True


class UserSettings(BaseModel):
    """Persisted application-level settings (per-install, no accounts)."""

    output_mode: Literal["fidelity", "clean"] = "fidelity"
    ocr_mode: Literal["auto", "always", "never"] = "auto"
    preserve_boundaries: bool = True
    extract_images: bool = True
    convert_tables: bool = True
    preserve_links: bool = True


DEFAULT_SETTINGS = UserSettings()


def settings_to_dict(s: UserSettings | ConversionSettings) -> dict:
    return s.model_dump()
