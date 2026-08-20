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
        utime(old / "document.md", (stamp, stamp))
        fresh_stamp = datetime.now(UTC).timestamp()
        utime(fresh, (fresh_stamp, fresh_stamp))
        utime(fresh / "document.md", (fresh_stamp, fresh_stamp))

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

    def test_running_job_output_kept_even_when_old(self, tmp_path: Path):
        from os import utime

        from app.core.config import settings
        from app.core.db import SessionLocal
        from app.models.job import Job

        output_root = settings.resolve_output_dir()
        job_dir = output_root / "activerun"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "document.md").write_text("# running", encoding="utf-8")
        past = (datetime.now(UTC) - timedelta(days=30)).timestamp()
        utime(job_dir, (past, past))
        utime(job_dir / "document.md", (past, past))

        db = SessionLocal()
        try:
            db.add(Job(id="activerun", status="running", items_json="[]", files_json="[]"))
            db.commit()
        finally:
            db.close()

        deleted, _ = storage.run_retention(now=datetime.now(UTC))
        assert deleted == 0
        assert job_dir.exists()

    def test_edited_output_kept_when_file_is_newer(self, tmp_path: Path):
        from os import utime

        from app.core.config import settings

        output_root = settings.resolve_output_dir()
        job_dir = output_root / "editedjob"
        job_dir.mkdir(parents=True, exist_ok=True)
        markdown = job_dir / "document.md"
        markdown.write_text("# edited", encoding="utf-8")
        past = (datetime.now(UTC) - timedelta(days=30)).timestamp()
        utime(job_dir, (past, past))
        recent = (datetime.now(UTC) - timedelta(hours=1)).timestamp()
        utime(markdown, (recent, recent))

        deleted, _ = storage.run_retention(now=datetime.now(UTC))
        assert deleted == 0
        assert job_dir.exists()

    def test_old_finished_output_deleted(self, tmp_path: Path):
        from os import utime

        from app.core.config import settings
        from app.core.db import SessionLocal
        from app.models.job import Job

        output_root = settings.resolve_output_dir()
        job_dir = output_root / "olddone"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "document.md").write_text("# done", encoding="utf-8")
        past = (datetime.now(UTC) - timedelta(days=30)).timestamp()
        utime(job_dir, (past, past))
        utime(job_dir / "document.md", (past, past))

        db = SessionLocal()
        try:
            db.add(Job(id="olddone", status="completed", items_json="[]", files_json="[]"))
            db.commit()
        finally:
            db.close()

        deleted, _ = storage.run_retention(now=datetime.now(UTC))
        assert deleted == 1
        assert not job_dir.exists()

    def test_upload_rows_pruned_when_files_gone(self, tmp_path: Path):
        from app.core.db import SessionLocal
        from app.models.job import Job, UploadedFile

        db = SessionLocal()
        try:
            db.add(
                UploadedFile(
                    id="orphanfile", name="gone.pdf", size=1, format="pdf",
                    sha256="a" * 64,
                )
            )
            db.add(
                UploadedFile(
                    id="referenced", name="kept.pdf", size=1, format="pdf",
                    sha256="b" * 64,
                )
            )
            db.add(
                Job(
                    id="referrer", status="completed", items_json="[]",
                    files_json=(
                        '[{"id": "referenced", "name": "kept.pdf", "size": 1, "format": "pdf"}]'
                    ),
                )
            )
            db.commit()
        finally:
            db.close()

        removed = storage.prune_uploaded_files()
        assert removed == 1

        db = SessionLocal()
        try:
            assert db.get(UploadedFile, "orphanfile") is None
            assert db.get(UploadedFile, "referenced") is not None
        finally:
            db.close()

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
