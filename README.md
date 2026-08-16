# Markforge

A local-first document-to-Markdown conversion platform. Convert **PDF, DOCX, PPTX and XLSX** files into clean, structured Markdown — entirely on your own machine. No cloud, no uploads to third parties, no lock-in.

![build](https://img.shields.io/badge/build-passing-brightgreen) ![stack](https://img.shields.io/badge/FastAPI-009688) ![stack](https://img.shields.io/badge/Next.js-000000) ![stack](https://img.shields.io/badge/SQLite-003B57)

## Features

- **Four formats**: PDF (text + image extraction with optional OCR), DOCX, PPTX, XLSX.
- **Common Document Model**: every converter produces a unified block-based document that one renderer turns into Markdown — deterministic and testable.
- **Two output modes**: *Fidelity* (keeps pages/slides/sheets visible) and *Clean Markdown* (flows content with fewer artifacts).
- **Deep Office extraction**: DOCX comments and tracked changes (insertions kept, deletions dropped), PPTX charts turned into tables, XLSX charts and cell comments, PDF two-column reading order.
- **Optional OCR** for scanned PDFs (Tesseract, automatic per-page detection).
- **Workspace**: per-file progress, warnings, stats; then edit the generated Markdown in a real editor with live preview, save back to the output directory, and download `.md` files or a ZIP of the whole job.
- **Local-first**: everything stays on your machine; jobs, uploads and results live in a configurable data directory. Optional LAN mode with password gate (brute-force rate limited).
- **Batch jobs**: convert many files at once, track each file independently.
- **Production hardening**: per-install secret key, rate-limited authentication, sanitized filenames, 96 backend tests, end-to-end Playwright suite, GitHub Actions CI.
- **Docker Compose** one-command deployment.

## Architecture

```
┌───────────────────┐        ┌───────────────────────────────────────────┐
│  Next.js (3000)   │  /api  │           FastAPI backend (3001)          │
│  React 19 +       │ ─────► │  uploads → jobs → converter pipeline      │
│  Tailwind +       │  proxy │  ┌───────────┐   ┌──────────┐             │
│  CodeMirror       │        │  │ converters│──►│ renderer │             │
└───────────────────┘        │  │ pdf/docx │   │ markdown │             │
                             │  │ pptx/xlsx│   │ cleanup  │             │
                             │  └───────────┘   └──────────┘             │
                             │  jobs persisted in SQLite (WAL)           │
                             │  outputs in ./storage/outputs/<job_id>/   │
                             └───────────────────────────────────────────┘
```

- `backend/app` — FastAPI application (routes, services, models, settings).
- `backend/converters` — one converter per format, all emitting the CDM.
- `backend/document_model` — the Common Document Model (blocks, metadata).
- `backend/markdown` — renderer and post-processing cleanup.
- `frontend/` — Next.js app: dashboard, job workspace, history.

## Quick start

### Option A — Docker Compose (recommended)

```bash
docker compose up --build -d
# frontend:  http://localhost:3000
# backend:   http://localhost:3001/api/health
```

### Option B — Manual

Backend (Python 3.10+):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
pip install -r requirements-ocr.txt   # optional: OCR support
uvicorn app.main:app --host 127.0.0.1 --port 3001
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000, proxies /api to :3001
```

## Configuration

All settings are environment variables with a `MARKFORGE_` prefix (see `.env.example`). Key ones:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MARKFORGE_DATA_DIR` | `./storage` | Base data directory (uploads, outputs, db) |
| `MARKFORGE_JOB_MODE` | `sync` | `sync` (in-process threads) or `celery` |
| `MARKFORGE_REDIS_URL` | `redis://localhost:6379/0` | Broker for Celery mode |
| `MARKFORGE_LAN_MODE` | `false` | Allow access from other devices |
| `MARKFORGE_LAN_PASSWORD` | *(empty)* | Password gate when LAN mode is on |
| `MARKFORGE_MAX_FILE_MB` | `100` | Per-file upload limit |
| `MARKFORGE_MAX_FILES_PER_JOB` | `25` | Max files per job |
| `MARKFORGE_RETENTION_PERIOD` | `7` | Days before outputs are cleaned up |
| `MARKFORGE_SECRET_KEY` | generated | Leave empty to auto-generate a per-install key in `<DATA_DIR>/.secret_key` |

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/files/upload` | Upload files (multipart), dedup by SHA-256 |
| `POST` | `/api/jobs` | Create a job from uploaded file ids |
| `GET` | `/api/jobs/{id}` | Poll job + per-file progress |
| `GET` | `/api/jobs/{id}/preview` | Extracted Markdown for a file |
| `PUT` | `/api/jobs/{id}/markdown` | Save edited Markdown back to output dir |
| `GET` | `/api/jobs/{id}/download` | Download a single `.md` |
| `GET` | `/api/jobs/{id}/zip` | Download all results as a ZIP |
| `GET` | `/api/jobs/history` | Recent jobs |
| `DELETE` | `/api/jobs/{id}` | Delete job + storage |
| `GET` | `/api/settings` · `PUT` | Read / save default conversion settings |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/auth/verify` | LAN password verification |

Interactive docs at `http://localhost:3001/docs`.

## Testing

Backend (96 tests — unit + integration):

```bash
cd backend
.venv\Scripts\python.exe -m pytest -q
```

End-to-end (Playwright, needs backend venv + Chrome):

```bash
cd frontend
npm run test:e2e
```

The e2e suite boots both servers with an isolated data directory, generates fixture
documents, and covers the full journey: upload → convert → preview → edit → save →
download → history → delete, including batch conversion of all four formats.

CI runs ruff, the full backend suite, frontend lint + build, and the Playwright
suite on every push to `main` (see `.github/workflows/ci.yml`).

## Output format

- **Fidelity mode**: `---` separators between pages/slides/sheets, headings derived from font size (PDF) or styles (DOCX/PPTX).
- **Tables** become GitHub-flavored Markdown tables; merged cells are flattened with clear labels. Charts (PPTX/XLSX) become tables too.
- **Comments and tracked changes** (DOCX): comments render as blockquotes with author + date; inserted text is kept, deleted text is removed.
- **Images** are extracted into `assets/` and referenced; links, footnotes and emphasis are preserved.
- Warnings (skipped images, unsupported objects, OCR availability, tracked changes) are surfaced per file in the UI and never fail a job silently.

## Security

- Filenames are sanitized on upload; content is never executed.
- The LAN password endpoint is rate limited (5 attempts / 60 s per IP).
- A per-install secret key is generated on first run and stored outside the repo.
- Jobs, uploads and outputs are removed on job deletion; retention cleanup runs on startup.

## License

MIT — see [LICENSE](LICENSE).
