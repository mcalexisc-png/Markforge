# Markforge

A local-first document-to-Markdown conversion platform. Convert **PDF, DOCX, PPTX and XLSX** files into clean, structured Markdown — entirely on your own machine. No cloud, no uploads to third parties, no lock-in.

![build](https://img.shields.io/badge/build-passing-brightgreen) ![stack](https://img.shields.io/badge/FastAPI-009688) ![stack](https://img.shields.io/badge/Next.js-000000) ![stack](https://img.shields.io/badge/SQLite-003B57)

## Features

- **Fifteen formats**: PDF (with optional OCR), DOCX, PPTX, XLSX, EPUB, Outlook `.msg`, HTML, CSV/TSV, JSON, XML, Markdown, plain text and Jupyter notebooks.
- **Figure extraction**: embedded images are saved to `assets/` next to the Markdown, referenced inline, deduplicated by content hash, and filtered so logos, rules and spacer pixels do not survive.
- **MarkItDown engine**: Microsoft's MarkItDown library does the conversion, wrapped with a column-aware PDF reader and font-size heading detection for PDFs and PPTX.
- **Two output modes**: *Fidelity* (keeps page/slide markers) and *Clean Markdown* (flows content with fewer artifacts).
- **Deck-friendly PDFs**: duplicate slide pages (animation builds) are removed, image-only pages are skipped with a placeholder, and two-column pages keep their reading order.
- **Optional OCR** for scanned PDFs (Tesseract, automatic per-page detection).
- **Full-text search** across every document you have ever converted, powered by SQLite FTS5.
- **Workspace**: per-file progress, warnings, stats; then edit the generated Markdown in a real editor with live preview, save back to the output directory, and download `.md` files or a ZIP of the whole job.
- **Local-first**: everything stays on your machine; jobs, uploads and results live in a configurable data directory. Optional LAN mode with password gate (brute-force rate limited).
- **Batch jobs**: convert many files at once, track each file independently, with per-upload progress and cancel.
- **Live progress**: job state streams over Server-Sent Events instead of per-second polling.
- **Production hardening**: per-install secret key, rate-limited authentication, sanitized filenames, 161 backend tests, end-to-end Playwright suite, GitHub Actions CI.
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

Backend (Python 3.11+):

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
| `MARKFORGE_DATA_DIR` | *(unset)* | Base data directory; db, uploads, outputs and temp all derive from it |
| `MARKFORGE_JOB_MODE` | `sync` | `sync` (in-process threads) or `celery` |
| `MARKFORGE_REDIS_URL` | `redis://localhost:6379/0` | Broker for Celery mode |
| `MARKFORGE_LAN_MODE` | `false` | Allow access from other devices |
| `MARKFORGE_LAN_PASSWORD` | *(empty)* | Password gate when LAN mode is on |
| `MARKFORGE_MAX_FILE_MB` | `100` | Per-file upload limit in MB (alias for `MARKFORGE_MAX_FILE_SIZE`) |
| `MARKFORGE_MAX_FILES_PER_JOB` | `25` | Max files per job |
| `MARKFORGE_RETENTION_PERIOD` | `7` | Days before outputs are cleaned up |
| `MARKFORGE_SECRET_KEY` | generated | Leave empty to auto-generate a per-install key in `<DATA_DIR>/.secret_key` |

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/files/upload` | Upload files (multipart), dedup by SHA-256 |
| `POST` | `/api/jobs` | Create a job from uploaded file ids |
| `GET` | `/api/jobs/{id}` | Poll job + per-file progress |
| `GET` | `/api/jobs/{id}/events` | Live job progress (Server-Sent Events) |
| `GET` | `/api/jobs/{id}/preview` | Extracted Markdown for a file |
| `GET` | `/api/jobs/{id}/assets/{file_id}/{name}` | Serve an extracted figure |
| `PUT` | `/api/jobs/{id}/markdown` | Save edited Markdown back to output dir |
| `GET` | `/api/jobs/{id}/download` | Download a single `.md` |
| `GET` | `/api/jobs/{id}/zip` | Download all results as a ZIP |
| `GET` | `/api/jobs/history` | Recent jobs |
| `GET` | `/api/search?q=` | Full-text search across all conversions |
| `DELETE` | `/api/jobs/{id}` | Delete job + storage |
| `GET` | `/api/settings` · `PUT` | Read / save default conversion settings |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/auth/verify` | LAN password verification |

Interactive docs at `http://localhost:3001/docs`.

## Testing

Backend (161 tests — unit + integration):

```bash
cd backend
.venv/bin/python -m pytest -q      # Windows: .venv\Scripts\python.exe -m pytest -q
```

Frontend unit tests (Vitest, 34 tests):

```bash
cd frontend
npm test
```

End-to-end (Playwright, needs backend venv + Chrome). Runs against both a
desktop and a phone viewport:

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
- **Links** are preserved as `[text](url)` (toggleable). Turning links off keeps extracted figures — only hyperlinks are flattened.
- **Figures** are written as `![alt](assets/image-001.png)` relative to the output directory, so a downloaded ZIP works offline unchanged.
- Warnings (duplicate pages removed, decorative pages skipped, OCR availability) are surfaced per file in the UI and never fail a job silently.

## Local-only guarantee

Markforge never sends your documents anywhere. Conversion, OCR, figure
extraction and search all run in-process on your machine, and the frontend
loads no external fonts, scripts or images.

This needs active defence rather than good intentions, because MarkItDown ships
converters that *do* reach the network — audio transcription uploads audio to
Google's Web Speech API, and there are URL fetchers and two Azure cloud
converters. Two independent layers keep them out:

1. **An explicit allowlist.** `ALLOWED_EXTENSIONS` in
   [`backend/converters/__init__.py`](backend/converters/__init__.py) names every
   accepted format. Audio, standalone images and archives are excluded by name.
2. **Explicit converter registration.** `build_local_engine()` in
   [`backend/converters/markitdown.py`](backend/converters/markitdown.py) builds
   the engine with `enable_builtins=False` and registers only local converters,
   so a networked converter cannot be reached even by a file nested inside an
   archive.

`TestEngineIsLocalOnly` in `backend/tests/unit/test_security.py` fails the build
if a networked converter is ever registered. To audit an install yourself:

```bash
grep -nE "Audio|YouTube|Bing|Wikipedia|Rss|DocumentIntelligence" backend/converters/markitdown.py
```

Matches should appear only in the explanatory comment and in the
`NETWORK_CONVERTER_NAMES` deny-list — never on a `register_converter` line.

## Security

- Filenames are sanitized on upload; content is never executed.
- Extracted figures are served only from their own job's `assets/` directory,
  through a route that refuses path traversal and non-image files.
- The LAN password endpoint is rate limited (5 attempts / 60 s per IP).
- A per-install secret key is generated on first run and stored outside the repo.
- Jobs, uploads and outputs are removed on job deletion; retention cleanup runs on startup.

## License

MIT — see [LICENSE](LICENSE).
