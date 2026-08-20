# Markforge

A local-first document-to-Markdown conversion platform. Convert **PDF, DOCX, PPTX and XLSX** files into clean, structured Markdown — entirely on your own machine. No cloud, no uploads to third parties, no lock-in.

![build](https://img.shields.io/badge/build-passing-brightgreen) ![stack](https://img.shields.io/badge/FastAPI-009688) ![stack](https://img.shields.io/badge/Next.js-000000) ![stack](https://img.shields.io/badge/SQLite-003B57)

## Features

- **Four formats**: PDF (text extraction with optional OCR), DOCX, PPTX, XLSX.
- **MarkItDown engine**: Microsoft's MarkItDown library does the conversion, wrapped with a column-aware PDF reader and font-size heading detection for PDFs and PPTX.
- **Two output modes**: *Fidelity* (keeps page/slide markers) and *Clean Markdown* (flows content with fewer artifacts).
- **Deck-friendly PDFs**: duplicate slide pages (animation builds) are removed, image-only pages are skipped with a placeholder, and two-column pages keep their reading order.
- **Optional OCR** for scanned PDFs (Tesseract, automatic per-page detection).
- **Workspace**: per-file progress, warnings, stats; then edit the generated Markdown in a real editor with live preview, save back to the output directory, and download `.md` files or a ZIP of the whole job.
- **Local-first**: everything stays on your machine; jobs, uploads and results live in a configurable data directory. Optional LAN mode with password gate (brute-force rate limited).
- **Batch jobs**: convert many files at once, track each file independently.
- **Production hardening**: per-install secret key, rate-limited authentication, sanitized filenames, 80 backend tests, end-to-end Playwright suite, GitHub Actions CI.
- **Docker Compose** one-command deployment.

## Architecture

```
┌───────────────────┐        ┌───────────────────────────────────────────┐
│  Next.js (3000)   │  /api  │           FastAPI backend (3001)          │
│  React 19 +       │ ─────► │  uploads → jobs → converter pipeline      │
│  Tailwind +       │  proxy │  ┌──────────────────┐                     │
│  CodeMirror       │        │  │ MarkItDown engine│  filters + cleanup  │
└───────────────────┘        │  │ (+ OCR pre-pass) │                     │
                             │  └──────────────────┘                     │
                             │  jobs persisted in SQLite (WAL)           │
                             │  outputs in ./storage/outputs/<job_id>/   │
                             └───────────────────────────────────────────┘
```

- `backend/app` — FastAPI application (routes, services, models, settings).
- `backend/converters` — MarkItDown adapter, custom PDF/PPTX converters, OCR and dedupe helpers.
- `backend/markdown` — post-conversion filters (boundaries, tables, links) and cleanup.
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

Backend (80 tests — unit + integration):

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

- **Fidelity mode**: page/slide/sheet markers kept; *Clean Markdown* strips them and flows content together.
- **Tables** become GitHub-flavored Markdown tables (`Convert tables` toggle turns them into plain text).
- **Headings** are derived from font size in PDFs (≥1.2× body) and PPTX, so decks without proper title placeholders still get structure.
- **Links** are preserved as `[text](url)` (toggleable); the output is always text-only Markdown.
- Warnings (duplicate pages removed, decorative pages skipped, OCR availability) are surfaced per file in the UI and never fail a job silently.

## Security

- Filenames are sanitized on upload; content is never executed.
- The LAN password endpoint is rate limited (5 attempts / 60 s per IP).
- A per-install secret key is generated on first run and stored outside the repo.
- Jobs, uploads and outputs are removed on job deletion; retention cleanup runs on startup.

## License

MIT — see [LICENSE](LICENSE).
