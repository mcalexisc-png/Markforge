"""Structured logging for the backend and workers.

Document content is never logged. Only job ids, filenames, formats, phases,
elapsed times and error types are emitted as structured key/value records.
"""

from __future__ import annotations

import logging
import logging.config
import sys

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
        "job": {
            "format": (
                "%(asctime)s %(levelname)s job=%(job_id)s file=%(filename)s "
                "format=%(format)s worker=%(worker)s stage=%(stage)s "
                "elapsed=%(elapsed).1fs warnings=%(warning_count)d "
                "%(message)s"
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "structured",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}


def configure_logging(level: str = "INFO") -> None:
    LOGGING_CONFIG["root"]["level"] = level.upper()
    logging.config.dictConfig(LOGGING_CONFIG)


class JobLoggerAdapter(logging.LoggerAdapter):
    """Adds consistent job context to every log record."""

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        kwargs.setdefault("extra", {}).update(self.extra)
        return msg, kwargs


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def job_logger(name: str, **context) -> JobLoggerAdapter:
    defaults = {
        "job_id": "-",
        "filename": "-",
        "format": "-",
        "worker": "-",
        "stage": "-",
        "elapsed": 0.0,
        "warning_count": 0,
    }
    defaults.update(context)
    return JobLoggerAdapter(logging.getLogger(name), defaults)
