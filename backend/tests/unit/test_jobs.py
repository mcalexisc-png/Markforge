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
    def test_dispatch_queues_when_slots_full(self, monkeypatch):
        monkeypatch.setattr(jobs_module, "_job_slots", threading.BoundedSemaphore(1))
        monkeypatch.setattr(jobs_module, "_queue_slots", threading.BoundedSemaphore(8))
        assert jobs_module._job_slots.acquire(blocking=False)

        # A full run slot must not fail the request: the job waits in a queue.
        threads_before = set(threading.enumerate())
        jobs_module.dispatch_job("queued-job")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if any(t.is_alive() for t in set(threading.enumerate()) - threads_before):
                break
            time.sleep(0.01)
        assert any(t.is_alive() for t in set(threading.enumerate()) - threads_before), (
            "a waiting thread must be started"
        )

        jobs_module._job_slots.release()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if not any(t.is_alive() for t in set(threading.enumerate()) - threads_before):
                break
            time.sleep(0.01)
        assert not any(t.is_alive() for t in set(threading.enumerate()) - threads_before)

    def test_dispatch_rejected_when_queue_full(self, monkeypatch):
        monkeypatch.setattr(jobs_module, "_job_slots", threading.BoundedSemaphore(1))
        monkeypatch.setattr(jobs_module, "_queue_slots", threading.BoundedSemaphore(1))
        assert jobs_module._queue_slots.acquire(blocking=False)

        with pytest.raises(HTTPException) as err:
            jobs_module.dispatch_job("some-job")
        assert err.value.status_code == 409

        jobs_module._queue_slots.release()
        # With a free queue slot the dispatch itself must not raise, even for
        # a job that does not exist (the worker thread logs and exits, then
        # returns its queue slot).
        jobs_module.dispatch_job("missing-job")
        deadline = time.monotonic() + 2
        released = False
        while time.monotonic() < deadline:
            if jobs_module._queue_slots.acquire(blocking=False):
                released = True
                break
            time.sleep(0.01)
        assert released, "the finished worker thread must free its queue slot"
        jobs_module._queue_slots.release()