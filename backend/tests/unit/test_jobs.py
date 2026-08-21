"""Unit tests for job dispatch limits and the conversion timeout."""

from __future__ import annotations

import threading
import time

import pytest

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

        # The service layer raises a domain error; mapping it to 409 is the
        # route's job (see TestQueueOverflow in the integration suite).
        with pytest.raises(jobs_module.QueueFullError):
            jobs_module.dispatch_job("some-job")

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

class TestJobFileOrder:
    def test_items_follow_the_order_the_user_chose(self, tmp_path):
        """Workspace tabs and ZIP contents must match the upload order.

        ``create_job`` looks the files up with a single ``IN`` query, which
        returns them in primary-key order. Ids are random hex, so iterating the
        query result directly shuffles the job relative to what the user picked.
        """
        import uuid

        from app.core.db import SessionLocal
        from app.models.job import UploadedFile
        from app.services import jobs as job_service

        db = SessionLocal()
        try:
            # Insert with ids that sort the opposite way to insertion order, so
            # a regression cannot pass by accident.
            ids = ["zzz" + uuid.uuid4().hex[:9], "aaa" + uuid.uuid4().hex[:9]]
            for index, file_id in enumerate(ids):
                db.add(
                    UploadedFile(
                        id=file_id,
                        name=f"file{index}.pdf",
                        size=10,
                        format="pdf",
                        sha256=uuid.uuid4().hex,
                    )
                )
            db.commit()
        finally:
            db.close()

        job = job_service.create_job(ids, {})
        out = job_service.to_job_out(job)
        assert [f.id for f in out.files] == ids
        assert [item.file_id for item in out.items] == ids
