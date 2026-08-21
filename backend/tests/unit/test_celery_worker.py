"""Tests for the Celery job path (workers/).

No broker is needed: dispatch routing is asserted with a stub, and the
registered task itself is executed inline via ``Task.apply``.
"""

from __future__ import annotations

from pathlib import Path

from fixtures.make_fixtures import make_pdf

from app.core.config import settings
from app.services.jobs import create_job, dispatch_job, get_job
from workers.celery_app import celery_app
from workers.conversion_worker import ConversionTask


def _upload_pdf(client, tmp_path: Path, name: str) -> dict:
    path = make_pdf(tmp_path / name)
    with open(path, "rb") as handle:
        response = client.post(
            "/api/files/upload", files=[("files", (name, handle, "application/pdf"))]
        )
    assert response.status_code == 200, response.text
    return response.json()[0]


class TestCeleryConfig:
    def test_task_registered_under_expected_name(self):
        assert "markforge.process_job" in celery_app.tasks

    def test_time_limits_derived_from_settings(self):
        assert celery_app.conf.task_soft_time_limit >= 60
        assert celery_app.conf.task_time_limit > celery_app.conf.task_soft_time_limit

    def test_late_acks_and_reject_on_worker_lost(self):
        # A lost worker must put the job back on the queue rather than
        # silently dropping it, and must not prefetch more than it can run.
        assert celery_app.conf.task_acks_late is True
        assert celery_app.conf.task_reject_on_worker_lost is True
        assert celery_app.conf.worker_prefetch_multiplier == 1


class TestDispatch:
    def test_celery_mode_sends_named_task(self, monkeypatch):
        captured: dict = {}

        def fake_send(name, args=None, **kwargs):
            captured["name"] = name
            captured["args"] = args

        monkeypatch.setattr(celery_app, "send_task", fake_send)
        monkeypatch.setattr(settings, "job_mode", "celery")
        dispatch_job("job-abc")
        assert captured == {"name": "markforge.process_job", "args": ["job-abc"]}

    def test_sync_mode_does_not_touch_celery(self, monkeypatch):
        sent = []
        monkeypatch.setattr(celery_app, "send_task", lambda *a, **k: sent.append(a))
        monkeypatch.setattr(settings, "job_mode", "sync")
        # The daemon thread will fail on the unknown job_id, but the key
        # assertion is that send_task is never invoked.
        dispatch_job("fake-job-id")
        assert sent == []


class TestWorkerTask:
    def test_runs_a_real_job_end_to_end(self, client, tmp_path):
        uploaded = _upload_pdf(client, tmp_path, "worker.pdf")
        job = create_job([uploaded["id"]], {})

        result = ConversionTask().apply(args=[job.id])
        assert result.successful()

        finished = get_job(job.id)
        assert finished is not None
        assert finished.status == "completed"

    def test_unknown_job_id_is_a_noop(self):
        # A job row can vanish between enqueue and execution (retention,
        # manual delete); the worker must log and move on, not crash.
        ConversionTask().run("does-not-exist")
