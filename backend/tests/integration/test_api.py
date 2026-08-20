"""Integration tests: upload -> queue -> conversion -> result -> download."""

from __future__ import annotations

import time
from pathlib import Path

from fixtures.make_fixtures import make_docx, make_pdf, make_pptx, make_xlsx


def upload(client, name: str, path: Path) -> dict:
    with open(path, "rb") as handle:
        response = client.post("/api/files/upload", files=[("files", (name, handle))])
    assert response.status_code == 200, response.text
    return response.json()[0]


def run_job(client, file_ids: list[str], settings: dict | None = None):
    response = client.post("/api/jobs", json={"file_ids": file_ids, "settings": settings or {}})
    assert response.status_code == 201, response.text
    job = response.json()
    for _ in range(150):
        poll = client.get(f"/api/jobs/{job['id']}")
        assert poll.status_code == 200
        state = poll.json()
        if state["status"] in ("completed", "partial", "failed"):
            return state
        time.sleep(0.1)
    raise AssertionError("job did not finish in time")


def upload_from(make_fn, tmp_path: Path, name: str) -> Path:
    return make_fn(tmp_path / name)


class TestUploadValidation:
    def test_unsupported_extension(self, client):
        response = client.post(
            "/api/files/upload", files=[("files", ("evil.txt", b"hello", "text/plain"))]
        )
        assert response.status_code == 400
        assert "Unsupported" in response.json()["detail"]

    def test_mime_mismatch(self, client, tmp_path):
        source = tmp_path / "fake.pdf"
        source.write_bytes(b"PK\x03\x04 not really a pdf at all")
        response = client.post(
            "/api/files/upload", files=[("files", ("fake.pdf", source.read_bytes(), "application/pdf"))]
        )
        assert response.status_code == 400

    def test_not_a_pdf(self, client):
        response = client.post(
            "/api/files/upload", files=[("files", ("plain.pdf", b"just text", "application/pdf"))]
        )
        assert response.status_code == 400

    def test_path_traversal_name(self, client):
        response = client.post(
            "/api/files/upload", files=[("files", ("..\\..\\evil.pdf", b"%PDF-1.7 fake", "application/pdf"))]
        )
        assert response.status_code == 200
        assert ".." not in response.json()[0]["name"]

    def test_reserved_device_name_rejected(self, client):
        response = client.post(
            "/api/files/upload",
            files=[("files", ("con.pdf", b"%PDF-1.7 fake", "application/pdf"))],
        )
        assert response.status_code == 400
        assert "reserved" in response.json()["detail"]

    def test_file_count_cap_enforced(self, client, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "max_files_per_job", 2)
        response = client.post(
            "/api/files/upload",
            files=[
                ("files", ("a.pdf", b"%PDF-1.7 fake", "application/pdf")),
                ("files", ("b.pdf", b"%PDF-1.7 fake", "application/pdf")),
                ("files", ("c.pdf", b"%PDF-1.7 fake", "application/pdf")),
            ],
        )
        assert response.status_code == 400
        assert "at most 2" in response.json()["detail"]

    def test_oversized_upload_rejected(self, client, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "max_file_size", 1024)
        response = client.post(
            "/api/files/upload",
            files=[("files", ("big.pdf", b"%PDF-1.7 " + b"x" * 4096, "application/pdf"))],
        )
        assert response.status_code == 400
        assert "size limit" in response.json()["detail"]


class TestConversionFlow:
    def test_pdf_flow(self, client, tmp_path):
        source = upload_from(make_pdf, tmp_path, "report.pdf")
        file_id = upload(client, "report.pdf", source)["id"]
        job = run_job(client, [file_id])
        assert job["status"] == "completed"
        assert job["items"][0]["stats"]["paragraphs"] >= 1
        self._assert_results(client, job)

    def test_docx_flow(self, client, tmp_path):
        source = upload_from(make_docx, tmp_path, "notes.docx")
        file_id = upload(client, "notes.docx", source)["id"]
        job = run_job(client, [file_id])
        assert job["status"] == "completed"
        assert job["items"][0]["stats"]["headings"] >= 1
        assert job["items"][0]["stats"]["tables"] >= 1
        self._assert_results(client, job)

    def test_pptx_flow(self, client, tmp_path):
        source = upload_from(make_pptx, tmp_path, "deck.pptx")
        file_id = upload(client, "deck.pptx", source)["id"]
        job = run_job(client, [file_id])
        assert job["status"] == "completed"
        assert job["items"][0]["stats"]["headings"] >= 3
        self._assert_results(client, job)

    def test_xlsx_flow(self, client, tmp_path):
        source = upload_from(make_xlsx, tmp_path, "grades.xlsx")
        file_id = upload(client, "grades.xlsx", source)["id"]
        job = run_job(client, [file_id])
        assert job["status"] == "completed"
        assert job["items"][0]["stats"]["tables"] >= 1
        self._assert_results(client, job)

    def test_markitdown_default_flow(self, client, tmp_path):
        source = upload_from(make_pdf, tmp_path, "md-report.pdf")
        file_id = upload(client, "md-report.pdf", source)["id"]
        job = run_job(client, [file_id])
        assert job["status"] == "completed"
        assert job["items"][0]["stats"]["paragraphs"] >= 1
        preview = client.get(f"/api/jobs/{job['id']}/preview")
        assert preview.status_code == 200
        assert "![" not in preview.json()["content"]
        download = client.get(f"/api/jobs/{job['id']}/download")
        assert download.status_code == 200

    def test_markitdown_all_toggles_off(self, client, tmp_path):
        source = upload_from(make_xlsx, tmp_path, "md-book.xlsx")
        file_id = upload(client, "md-book.xlsx", source)["id"]
        job = run_job(
            client,
            [file_id],
            settings={
                "output_mode": "clean",
                "preserve_boundaries": False,
                "convert_tables": False,
                "preserve_links": False,
                "ocr_mode": "never",
            },
        )
        assert job["status"] == "completed"
        preview = client.get(f"/api/jobs/{job['id']}/preview")
        assert preview.status_code == 200
        content = preview.json()["content"]
        assert "<!--" not in content
        assert "|" not in content
        assert "](" not in content

    def test_markitdown_deck_pdf_structure(self, client, tmp_path):
        from fixtures.make_fixtures import make_deck_pdf

        source = upload_from(make_deck_pdf, tmp_path, "deck.pdf")
        file_id = upload(client, "deck.pdf", source)["id"]
        job = run_job(
            client,
            [file_id],
            settings={"output_mode": "clean", "ocr_mode": "auto"},
        )
        assert job["status"] == "completed"
        codes = [w["code"] for w in job["items"][0]["warnings"]]
        assert "duplicate_pages_removed" in codes
        assert "decorative_pages_skipped" in codes
        preview = client.get(f"/api/jobs/{job['id']}/preview")
        assert preview.status_code == 200
        content = preview.json()["content"]
        assert "## Mission 1" in content
        assert "<!--" not in content
        assert "[Slide image — no text]" in content
        assert content.count("Mission 3") == 1

    def _assert_results(self, client, job):
        job_id = job["id"]
        preview = client.get(f"/api/jobs/{job_id}/preview")
        assert preview.status_code == 200
        assert "#" in preview.json()["content"]

        download = client.get(f"/api/jobs/{job_id}/download")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("text/markdown")

        zip_response = client.get(f"/api/jobs/{job_id}/zip")
        assert zip_response.status_code == 200
        assert zip_response.headers["content-type"] == "application/zip"
        assert b"document.md" in zip_response.content

        delete = client.delete(f"/api/jobs/{job_id}")
        assert delete.status_code == 204
        gone = client.get(f"/api/jobs/{job_id}")
        assert gone.status_code == 404

    def test_batch_flow(self, client, tmp_path):
        pdf = upload(client, "report.pdf", upload_from(make_pdf, tmp_path, "report.pdf"))["id"]
        xlsx = upload(client, "grades.xlsx", upload_from(make_xlsx, tmp_path, "grades.xlsx"))["id"]
        job = run_job(client, [pdf, xlsx])
        assert job["status"] == "completed"
        assert all(i["status"] == "completed" for i in job["items"])
        zip_response = client.get(f"/api/jobs/{job['id']}/zip")
        assert zip_response.status_code == 200

    def test_failed_file_keeps_job_partial(self, client, tmp_path):
        import io
        import zipfile

        good = upload(client, "good.pdf", upload_from(make_pdf, tmp_path, "good.pdf"))["id"]
        bad_path = tmp_path / "broken.docx"
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" ContentType="'
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
            "</Types>"
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("word/document.xml", "<not-valid-xml")
        bad_path.write_bytes(buffer.getvalue())
        bad = upload(client, "broken.docx", bad_path)["id"]
        job = run_job(client, [good, bad])
        statuses = {i["status"] for i in job["items"]}
        assert statuses == {"completed", "failed"}
        assert job["status"] == "partial"
        failed_item = next(i for i in job["items"] if i["status"] == "failed")
        assert failed_item["error"]["code"] in ("corrupt_file", "conversion_failed")

    def test_edit_markdown_flow(self, client, tmp_path):
        source = upload_from(make_pdf, tmp_path, "editable.pdf")
        file_id = upload(client, "editable.pdf", source)["id"]
        job = run_job(client, [file_id])
        assert job["status"] == "completed"
        job_id = job["id"]

        original = client.get(f"/api/jobs/{job_id}/preview").json()["content"]
        edited = "# My edits\n\n" + original
        saved = client.put(f"/api/jobs/{job_id}/markdown", json={"content": edited})
        assert saved.status_code == 204

        job_after = client.get(f"/api/jobs/{job_id}").json()
        assert job_after["items"][0]["edited"] is True

        preview = client.get(f"/api/jobs/{job_id}/preview")
        assert preview.status_code == 200
        assert preview.json()["content"] == edited

        download = client.get(f"/api/jobs/{job_id}/download")
        assert download.status_code == 200
        assert b"# My edits" in download.content

        missing = client.put("/api/jobs/does-not-exist/markdown", json={"content": "x"})
        assert missing.status_code == 404

    def test_uploads_removed_after_job(self, client, tmp_path):
        from pathlib import Path as P

        from app.core.config import settings

        source = upload_from(make_pdf, tmp_path, "cleanup.pdf")
        file_id = upload(client, "cleanup.pdf", source)["id"]
        run_job(client, [file_id])
        upload_dir = P(settings.resolve_upload_dir()) / file_id
        for _ in range(50):
            if not upload_dir.exists():
                break
            time.sleep(0.1)
        assert not upload_dir.exists()

    def test_same_stem_files_do_not_overwrite(self, client, tmp_path):
        pdf_id = upload(client, "report v1.pdf", upload_from(make_pdf, tmp_path, "report v1.pdf"))["id"]
        docx_id = upload(client, "report v1.docx", upload_from(make_docx, tmp_path, "report v1.docx"))["id"]
        job = run_job(client, [pdf_id, docx_id])
        assert job["status"] == "completed"
        assert all(i["status"] == "completed" for i in job["items"])
        assert job["items"][0]["output_dir"] != job["items"][1]["output_dir"]

        pdf_preview = client.get(f"/api/jobs/{job['id']}/preview", params={"file_id": pdf_id})
        docx_preview = client.get(f"/api/jobs/{job['id']}/preview", params={"file_id": docx_id})
        assert pdf_preview.status_code == 200
        assert docx_preview.status_code == 200
        assert "Chapter 1" in pdf_preview.json()["content"]
        assert "Sample Document" in docx_preview.json()["content"]

        zip_response = client.get(f"/api/jobs/{job['id']}/zip")
        assert zip_response.status_code == 200
        assert b"report v1/document.md" in zip_response.content
        assert b"report v1-2/document.md" in zip_response.content

    def test_save_markdown_unknown_file_id_rejected(self, client, tmp_path):
        pdf_id = upload(client, "one.pdf", upload_from(make_pdf, tmp_path, "one.pdf"))["id"]
        docx_id = upload(client, "two.docx", upload_from(make_docx, tmp_path, "two.docx"))["id"]
        job = run_job(client, [pdf_id, docx_id])
        job_id = job["id"]
        original = client.get(f"/api/jobs/{job_id}/preview", params={"file_id": pdf_id}).json()["content"]

        response = client.put(
            f"/api/jobs/{job_id}/markdown",
            json={"file_id": "does-not-exist", "content": "# nope"},
        )
        assert response.status_code == 404

        preview = client.get(f"/api/jobs/{job_id}/preview", params={"file_id": pdf_id})
        assert preview.status_code == 200
        assert preview.json()["content"] == original

    def test_reset_restores_original_extraction(self, client, tmp_path):
        source = upload_from(make_pdf, tmp_path, "reset.pdf")
        file_id = upload(client, "reset.pdf", source)["id"]
        job = run_job(client, [file_id])
        job_id = job["id"]
        original = client.get(f"/api/jobs/{job_id}/preview").json()["content"]

        edited = "# My edits\n\n" + original
        assert client.put(f"/api/jobs/{job_id}/markdown", json={"file_id": file_id, "content": edited}).status_code == 204

        reset = client.post(f"/api/jobs/{job_id}/reset", params={"file_id": file_id})
        assert reset.status_code == 200
        assert reset.json()["content"] == original

        preview = client.get(f"/api/jobs/{job_id}/preview")
        assert preview.json()["content"] == original

        edited_again = "## Re-edit\n\n" + original
        assert client.put(f"/api/jobs/{job_id}/markdown", json={"content": edited_again}).status_code == 204
        reset_no_id = client.post(f"/api/jobs/{job_id}/reset")
        assert reset_no_id.status_code == 200
        assert reset_no_id.json()["content"] == original


class TestHistoryAndSettings:
    def test_history(self, client, tmp_path):
        source = upload_from(make_pdf, tmp_path, "hist.pdf")
        file_id = upload(client, "hist.pdf", source)["id"]
        run_job(client, [file_id])
        response = client.get("/api/jobs/history")
        assert response.status_code == 200
        assert response.json()[0]["filename"] == "hist.pdf"
        assert response.json()[0]["status"] == "completed"

    def test_settings_roundtrip(self, client):
        put = client.put("/api/settings", json={"output_mode": "clean", "ocr_mode": "auto"})
        assert put.status_code == 200
        assert put.json()["output_mode"] == "clean"
        get = client.get("/api/settings")
        assert get.json()["output_mode"] == "clean"

    def test_corrupt_settings_fall_back_to_defaults(self, client):
        from app.core.db import SessionLocal
        from app.models.job import AppSetting

        db = SessionLocal()
        try:
            row = db.get(AppSetting, "user_settings")
            if row is None:
                row = AppSetting(key="user_settings", value="")
                db.add(row)
            row.value = "{this is not valid json"
            db.commit()
        finally:
            db.close()
        response = client.get("/api/settings")
        assert response.status_code == 200
        assert response.json()["output_mode"] == "fidelity"

    def test_health(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["storage"] == "writable"
        assert body["lan"]["enabled"] is False

    def test_duplicate_upload_deduped(self, client, tmp_path):
        source = make_pdf(tmp_path / "dup.pdf", title="Dedupe Collision Test")
        data = source.read_bytes()
        first = client.post("/api/files/upload", files=[("files", ("dup.pdf", data))])
        second = client.post("/api/files/upload", files=[("files", ("dup.pdf", data))])
        assert first.json()[0]["id"] == second.json()[0]["id"]
        assert second.json()[0]["duplicate_of"] == first.json()[0]["id"]


class TestZipEndpoint:
    def test_zip_rejected_while_job_running(self, client, tmp_path):
        from app.core.db import SessionLocal
        from app.models.job import Job

        file_id = upload(client, "zr.pdf", upload_from(make_pdf, tmp_path, "zr.pdf"))["id"]
        job = run_job(client, [file_id])
        db = SessionLocal()
        try:
            job_row = db.get(Job, job["id"])
            job_row.status = "running"
            db.commit()
        finally:
            db.close()
        response = client.get(f"/api/jobs/{job['id']}/zip")
        assert response.status_code == 409
        assert "still running" in response.json()["detail"]

    def test_zip_reused_when_results_unchanged(self, client, tmp_path):
        from app.services.storage import job_output_dir

        file_id = upload(client, "zu.pdf", upload_from(make_pdf, tmp_path, "zu.pdf"))["id"]
        job = run_job(client, [file_id])
        job_id = job["id"]
        zip_path = job_output_dir(job_id) / f"markforge-{job_id}.zip"

        assert client.get(f"/api/jobs/{job_id}/zip").status_code == 200
        first_mtime = zip_path.stat().st_mtime_ns

        assert client.get(f"/api/jobs/{job_id}/zip").status_code == 200
        assert client.get(f"/api/jobs/{job_id}/zip").status_code == 200
        assert zip_path.stat().st_mtime_ns == first_mtime, "unchanged results must reuse the existing archive"

        edited = client.get(f"/api/jobs/{job_id}/preview").json()["content"] + "\n# touched\n"
        assert client.put(f"/api/jobs/{job_id}/markdown", json={"content": edited}).status_code == 204
        assert client.get(f"/api/jobs/{job_id}/zip").status_code == 200
        assert zip_path.stat().st_mtime_ns > first_mtime, "edited results must refresh the archive"
