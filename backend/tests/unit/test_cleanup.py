"""Unit tests for storage cleanup, retention and temp handling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.services import storage


class TestRetention:
    def test_old_outputs_deleted(self, tmp_path: Path):
        from app.core.config import settings

        output_root = settings.resolve_output_dir()
        old = output_root / "oldjob"
        fresh = output_root / "freshjob"
        old.mkdir(parents=True, exist_ok=True)
        fresh.mkdir(parents=True, exist_ok=True)
        (old / "document.md").write_text("# old", encoding="utf-8")
        (fresh / "document.md").write_text("# fresh", encoding="utf-8")

        past = datetime.now(UTC) - timedelta(days=30)
        from os import utime

        stamp = past.timestamp()
        utime(old, (stamp, stamp))
        fresh_stamp = datetime.now(UTC).timestamp()
        utime(fresh, (fresh_stamp, fresh_stamp))

        deleted, freed = storage.run_retention(now=datetime.now(UTC))
        assert deleted == 1
        assert freed > 0
        assert not old.exists()
        assert fresh.exists()

    def test_fresh_outputs_kept(self, tmp_path: Path):
        from app.core.config import settings

        output_root = settings.resolve_output_dir()
        job = output_root / "keepme"
        job.mkdir(parents=True, exist_ok=True)
        (job / "document.md").write_text("# hi", encoding="utf-8")
        deleted, _ = storage.run_retention()
        assert deleted == 0
        assert job.exists()

    def test_temp_cleanup(self, tmp_path: Path):
        from app.core.config import settings

        temp_root = settings.resolve_temp_dir()
        stale = temp_root / "stale"
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "x.bin").write_bytes(b"x")
        from os import utime

        past = (datetime.now(UTC) - timedelta(days=5)).timestamp()
        utime(stale, (past, past))
        removed = storage.cleanup_temp()
        assert removed >= 1
        assert not stale.exists()

    def test_delete_job_storage(self):
        from app.core.config import settings
        from app.services.storage import job_output_dir, job_temp_dir, job_upload_dir

        job_id = "abc123"
        for maker in (job_output_dir, job_upload_dir, job_temp_dir):
            maker(job_id).mkdir(parents=True, exist_ok=True)
            (maker(job_id) / "file").write_bytes(b"x")
        storage.delete_job_storage(job_id)
        for sub in ("outputs", "uploads", "temp"):
            assert not (settings.resolve_storage_dir() / sub / job_id).exists()

    def test_dir_size(self):
        from app.core.config import settings

        job_dir = settings.resolve_output_dir() / "sizetest"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "a.md").write_bytes(b"12345")
        (job_dir / "b.md").write_bytes(b"12345")
        assert storage.dir_size(job_dir) == 10
