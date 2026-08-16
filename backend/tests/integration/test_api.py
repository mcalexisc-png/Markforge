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


class TestConversionFlow:
    def test_pdf_flow(self, client, tmp_path):
        source = upload_from(make_pdf, tmp_path, "report.pdf")
        file_id = upload(client, "report.pdf", source)["id"]
        job = run_job(client, [file_id])
        assert job["status"] == "completed"
        assert job["items"][0]["stats"]["pages"] == 3
        self._assert_results(client, job)

    def test_docx_flow(self, client, tmp_path):
        source = upload_from(make_docx, tmp_path, "notes.docx")
        file_id = upload(client, "notes.docx", source)["id"]
        job = run_job(client, [file_id])
        assert job["status"] == "completed"
        assert job["items"][0]["stats"]["headings"] >= 2
        assert job["items"][0]["stats"]["tables"] >= 1
        self._assert_results(client, job)

    def test_pptx_flow(self, client, tmp_path):
        source = upload_from(make_pptx, tmp_path, "deck.pptx")
        file_id = upload(client, "deck.pptx", source)["id"]
        job = run_job(client, [file_id])
        assert job["status"] == "completed"
        assert job["items"][0]["stats"]["slides"] == 3
        self._assert_results(client, job)

    def test_xlsx_flow(self, client, tmp_path):
        source = upload_from(make_xlsx, tmp_path, "grades.xlsx")
        file_id = upload(client, "grades.xlsx", source)["id"]
        job = run_job(client, [file_id])
        assert job["status"] == "completed"
        assert job["items"][0]["stats"]["sheets"] == 2
        self._assert_results(client, job)

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
        good = upload(client, "good.pdf", upload_from(make_pdf, tmp_path, "good.pdf"))["id"]
        bad_path = tmp_path / "broken.pdf"
        bad_path.write_bytes(b"%PDF-1.7\nthis is not a real pdf document content")
        bad = upload(client, "broken.pdf", bad_path)["id"]
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

    def test_health(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["storage"] == "writable"
        assert body["lan"]["enabled"] is False

    def test_duplicate_upload_deduped(self, client, tmp_path):
        source = upload_from(make_pdf, tmp_path, "dup.pdf")
        data = source.read_bytes()
        first = client.post("/api/files/upload", files=[("files", ("dup.pdf", data))])
        second = client.post("/api/files/upload", files=[("files", ("dup.pdf", data))])
        assert first.json()[0]["id"] == second.json()[0]["id"]
        assert second.json()[0]["duplicate_of"] == first.json()[0]["id"]
