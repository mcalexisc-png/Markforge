"""Unit tests for job dispatch limits and the conversion timeout."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi import HTTPException

from app.services import jobs as jobs_module
from app.services.jobs import _run_with_timeout


class TestTimeout:
    def test_timeout_raises_and_returns_quickly(self, monkeypatch):
        monkeypatch.setattr(jobs_module, "_MIN_TIMEOUT", 1)
        monkeypatch.setattr(jobs_module.settings, "job_timeout", 1)

        def hang() -> None:
            time.sleep(10)

        started = time.monotonic()
        with pytest.raises(TimeoutError):
            _run_with_timeout(hang)
        elapsed = time.monotonic() - started
        assert elapsed < 5

    def test_success_returns_value(self, monkeypatch):
        monkeypatch.setattr(jobs_module.settings, "job_timeout", 60)
        assert _run_with_timeout(lambda: 42) == 42


class TestConcurrencyCap:
    def test_dispatch_rejected_when_slots_full(self, monkeypatch):
        monkeypatch.setattr(jobs_module, "_job_slots", threading.BoundedSemaphore(1))
        assert jobs_module._job_slots.acquire(blocking=False)

        with pytest.raises(HTTPException) as err:
            jobs_module.dispatch_job("some-job")
        assert err.value.status_code == 409

        jobs_module._job_slots.release()
        # With a free slot the dispatch itself must not raise, even for a
        # job that does not exist (the thread logs and exits).
        threads_before = set(threading.enumerate())
        jobs_module.dispatch_job("missing-job")
        for _ in range(100):
            if not set(threading.enumerate()) - threads_before:
                break
            time.sleep(0.01)
        assert not set(threading.enumerate()) - threads_before