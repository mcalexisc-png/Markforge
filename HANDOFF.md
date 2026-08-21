# Markforge — Session Handoff

**Date:** 2026-08-21 · **Branch:** `main` (nothing committed — 50 files changed in the working tree)

This document is a complete handoff for continuing work on Markforge. Read the
**Gotchas** section before touching tests or the converter registration — several
non-obvious traps cost real time this session and are easy to re-introduce.

---

## 1. What Markforge is

A local-first document→Markdown converter. FastAPI backend (`:3001`) + Next.js 16 /
React 19 frontend (`:3000`), SQLite (WAL) for job state, filesystem for content.
The frontend proxies `/api/*` to the backend, so everything is same-origin.

```
frontend/ (Next 16 App Router, all client components)
backend/
  app/          FastAPI: api/ core/ models/ schemas/ services/
  converters/   MarkItDown adapter + custom PDF/PPTX converters + image extraction
  markdown/     post-conversion filters and cleanup
  document_model/  result metadata, stats, warnings
  workers/      Celery (optional, untested)
```

---

## 2. Current state — all green

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `cd backend && .venv/bin/python -m pytest -q` | **161 pass** (2 skipped) |
| Backend lint | `cd backend && .venv/bin/ruff check app converters document_model markdown tests workers` | pass |
| Frontend unit | `cd frontend && npm test` | **34 pass** |
| Frontend lint | `cd frontend && npm run lint` | pass |
| Typecheck | `cd frontend && npm run typecheck` | pass |
| Build | `cd frontend && npm run build` | pass |
| E2E | `cd frontend && npm run test:e2e` | **12 pass** (desktop + mobile) |
| Docker | `docker compose build && docker compose up -d` | both images build; data persists across recreate |

Baseline for comparison: before this session there were 106 backend tests, 0 frontend
unit tests, 4 e2e tests (**2 of which were already failing**), and the Docker build
was broken.

---

## 3. Work completed this session

### Upgrades (user picked 1, 2, 3, 5, 6 — deliberately **excluded 4**)

**1. Figure extraction** — `backend/converters/images.py` (new)
The asset pipeline existed but had been decapitated by the MarkItDown migration:
`ConversionContext.save_image()` had **zero callers**, while the ZIP packager, the
preview's `safeSrc()` guard, `ImageBlock.path` and `DocumentStats.images` all still
expected assets. Reconnected:
- PDF: PyMuPDF extraction anchored to existing `<!-- Page N -->` markers
- DOCX: MarkItDown emits a literal stub `![](data:image/png;base64...)` at each
  image's real position — replaced in place, so DOCX figures land inline
- PPTX: written inline by `HeadingPptxConverter`, which is the only place shape
  order still exists
- XLSX: no positional anchor available → grouped in a trailing `## Figures` section
- Noise filter (`is_decorative`): min dimension 64px, min area 100×100, max aspect
  20:1, min 1KB. Dedupe by content hash means a per-page logo costs one file.
- New setting `extract_images` (default on) on both settings models + UI switch
- New route `GET /api/jobs/{job_id}/assets/{file_id}/{name}` — traversal-safe,
  images only. Stored `.md` keeps **relative** paths so ZIPs stay portable; only
  the rendered preview rewrites them via `assetBase`.

**2. Formats: 4 → 15** — `backend/converters/__init__.py`
Added EPUB, Outlook `.msg`, HTML/HTM, CSV, TSV, JSON, XML, MD, TXT, `.ipynb`.
Deliberately excluded: audio, standalone images, `.zip` (see Gotchas).

**3. Full-text search** — `backend/app/services/search.py`, `routes_search.py` (new)
SQLite FTS5, filename weighted 8× over body via `bm25`, `snippet()` highlighting.
Index maintained on conversion, save and reset; dropped on delete and retention.
`backfill_missing()` indexes results that predate the feature. Search UI on `/jobs`
with debounced query, `<mark>` highlighting, and deep links (`?file=<id>`).

**5. SSE progress** — `GET /api/jobs/{job_id}/events`
Replaces 1 Hz polling. Bounded-backoff polling remains only as a fallback.

**6. Upload progress + cancel** — XHR with `upload.onprogress`, AbortController.

### Docker (was completely broken)

- `docker/Dockerfile.frontend` copied `/app/public`, which **did not exist** → build
  aborted. Created `frontend/public/` with favicon, manifest and robots.txt (also
  fixes the app having no favicon at all).
- `Dockerfile.backend` set `MARKFORGE_DATA_DIR`, `MARKFORGE_JOB_DIR`,
  `MARKFORGE_DB_PATH` — **none were Settings fields**, so `extra="ignore"` dropped
  them silently and data landed in `/storage`, outside the `/data` volume. Every
  container recreate destroyed all jobs.
- Fix: made `MARKFORGE_DATA_DIR` a **real** setting. When set, db/uploads/outputs/temp
  all derive from it; an explicitly-set path still wins (`Settings._path_for`).
  Also added `MARKFORGE_MAX_FILE_MB` as a real alias. Both were already documented
  in the README but did not exist.
- `docker-compose.yml`: `MARKFORGE_ENV` → `MARKFORGE_APP_ENV`.
- **Verified**: convert a doc → `docker compose down` → `up` → job, search index and
  extracted assets all still present.

### Bugs found and fixed along the way

1. **`create_job` discarded user file order** — iterated the DB result (primary-key
   order over random UUIDs) instead of `file_ids`. Workspace tabs and ZIP contents
   were effectively shuffled. Regression test added.
2. **Protocol-relative image bypass (security)** — `safeSrc()` allowed anything
   starting with `/`, so `//tracker.example/pixel.png` passed and the browser
   resolved it to an **external** request, defeating the local-only guarantee. A
   crafted document could beacon out on preview. Found by a unit test I wrote.
3. **`formatMeta[file.format]` unguarded** — latent white-screen crash, live the
   moment formats expanded.
4. **Inverted dashboard polling** — `enabled: history.length === 0` stopped
   refreshing as soon as any job existed, i.e. exactly when there was something
   to watch.
5. **Orphaned job rows** — the row was committed before `dispatch_job`, which can
   raise on queue overflow, leaving it permanently `queued`; retention only reaps
   terminal jobs, so its output directory was kept forever.
6. **Icon-only nav links had no accessible name on mobile** (label is
   `hidden sm:inline`).
7. **e2e harness race (pre-existing)** — see Gotchas §5.1.
8. **e2e locator ambiguity (pre-existing)** — see Gotchas §5.2.

### Hardening / cleanup

- Service layer no longer raises `HTTPException` (`QueueFullError`,
  `ConversionCapacityError` mapped in the route).
- Timed-out conversion threads are counted; past `_MAX_ABANDONED = 8` new jobs are
  refused with a clear error instead of leaking unboundedly. **Note:** Python
  cannot kill the threads; this bounds the damage, it does not fix it.
- Global 500 handler returns JSON `{detail}` (was plain text, so the frontend's
  error parser found nothing).
- CORS narrowed from `allow_origins=["*"]` to localhost + `MARKFORGE_CORS_ORIGINS`.
- **Schema migrations** — `run_migrations()` in `app/core/db.py` using SQLite's
  `PRAGMA user_version`. `create_all` never ALTERs, so any future column change to
  `jobs` would have broken existing installs. Append to `MIGRATIONS`; never edit or
  renumber an existing step.
- `/history` no longer `rglob`s every job per request — size recorded once at
  completion in `JobFileState.output_size` (falls back to walking for old jobs).
- Downloads stream via anchor + `Content-Disposition` instead of buffering the whole
  file into a Blob. Required adding `HEAD` support to `/download` and `/zip`
  (FastAPI does **not** auto-handle HEAD — it returned 405).
- Error boundaries: `app/error.tsx`, `app/global-error.tsx`, `app/not-found.tsx`.
- Unsaved-draft protection: `beforeunload` + `lib/unsaved.ts` registry consulted by
  the header nav and the workspace Back link (client-side nav never fires
  `beforeunload`). `dirty` now compares against a saved baseline instead of firing
  on any CodeMirror `onChange`.
- Complete ARIA patterns for `Tabs` (roving tabindex, `aria-controls`, matching ids)
  and the settings `RadioGroup` (arrow keys, roving tabindex).
- `Dialog` effect no longer depends on an inline `onOpenChange` (was tearing down
  and rebuilding on every keystroke, thrashing body overflow and stealing focus);
  latest callback read through a ref.
- Dead code removed: `document_model/blocks.py` (141 lines), `BaseConverter`,
  orphaned `ocr.py` functions, `ui/separator.tsx`, `ui/select.tsx`.
- `/{job_id}/status` kept as a documented alias rather than a duplicate handler.
- CI now runs `typecheck`, `npm test`, and lints `workers/`.

---

## 4. The local-only guarantee — do not regress this

The user's hard requirement: **the app must never send documents anywhere.**

MarkItDown's `enable_builtins()` registers converters that *do* reach the network:

| Converter | Egress |
| --- | --- |
| `AudioConverter` | `recognize_google()` — **uploads audio to Google's Web Speech API** |
| `YouTube` / `BingSerp` / `Wikipedia` / `Rss` | fetch remote URLs |
| `DocumentIntelligence` / `ContentUnderstanding` | Azure cloud |
| `_llm_caption` | OpenAI-compatible client |

Two independent layers keep them out:

1. **Named allowlist** — `ALLOWED_EXTENSIONS` in `backend/converters/__init__.py`.
2. **Explicit registration** — `build_local_engine()` in
   `backend/converters/markitdown.py` uses `MarkItDown(enable_builtins=False)` and
   adds back only local converters. This is what makes egress *structurally*
   impossible rather than merely unreachable — including for a file nested inside
   an archive.

`TestEngineIsLocalOnly` in `backend/tests/unit/test_security.py` fails the build if a
networked converter is ever registered. Audit:

```bash
grep -nE "Audio|YouTube|Bing|Wikipedia|Rss|DocumentIntelligence" backend/converters/markitdown.py
```

Matches must appear **only** in the explanatory comment and the
`NETWORK_CONVERTER_NAMES` deny-list — never on a `register_converter` line.

The frontend has **zero** external references (no Google Fonts, no CDN). Keep it so.

---

## 5. Gotchas — read before touching tests

### 5.1 The e2e harness deleted the database mid-run (fixed — don't undo)

`playwright.global-setup.ts` used to `rmSync` the e2e data directory. **Playwright
starts `webServer` before `globalSetup`**, so uvicorn had already created and opened
its SQLite file; deleting the directory left the server holding an unlinked inode and
the next connection it opened silently created an empty database →
`sqlite3.OperationalError: no such table: jobs`.

Baseline HEAD survived on a single pooled connection. Adding SSE and search writes
required more connections, which is why the symptom only appeared with the new code —
it looked exactly like a regression I had introduced. The wipe was also redundant:
`MARKFORGE_E2E_DATA` is unique per run. **Do not reinstate it.**

### 5.2 e2e projects share one backend and one data directory

`chromium` and `mobile` run against the same webServer.

- Fixture bytes are salted with `testInfo.project.name` because uploads are
  deduplicated by SHA-256 — identical bytes from the second project are detected as
  duplicates and never staged.
- Staged-file assertions are scoped with `stagedFiles(page)` (the
  "Files ready for conversion" list). A bare `getByText("notes.docx")` also matches
  the recent-conversions list and throws a strict-mode violation once history is
  non-empty.

### 5.3 Next.js 16 renamed the error-boundary prop

`frontend/AGENTS.md` (auto-generated by `next dev`) says to read
`node_modules/next/dist/docs/` before writing Next code. **Heed it.** The error
boundary prop is **`retry`**, not `reset` (stable since v16.3.0) — using `reset`
compiles, typechecks and builds, then throws at runtime when clicked. `global-error`
also gets no global styles and does not support `metadata` exports.

### 5.4 `httpx2` in `requirements-dev.txt` is correct

It looks like a typo for `httpx`. It is not — this Starlette version does
`import httpx2 as httpx` in `testclient.py`. `httpx` is not even installed. Leave it.

### 5.5 Don't abort in-flight uploads on unmount

React's dev StrictMode mounts → unmounts → remounts. An unmount cleanup calling
`abortRef.current?.abort()` cancels any upload started in that window, which made
uploads fail intermittently under automation. Cancelling stays an explicit user
action via the Cancel button.

### 5.6 PDF fixtures with identical page text get deduplicated

`dedupe_duplicate_pages` strips consecutive identical-text pages (animation builds).
A test fixture with the same text on every page collapses to one page. Give each page
unique text.

---

## 6. What is left

### Not done — explicitly out of scope

- **Upgrade 4 (local VLM figure captioning)** — the user excluded it twice. It is the
  only candidate that would introduce an outbound model call. Extracted figures
  currently get alt text like `Figure 1 on page 3`.

### Known remaining gaps

| Item | Where | Notes |
| --- | --- | --- |
| Celery path untested | `backend/workers/` | Now linted, still has no tests. `MARKFORGE_JOB_MODE=celery` is unexercised. |
| LAN middleware untested | `app/main.py:lan_access_middleware` | No test covers the cookie gate. |
| Timed-out threads still leak | `jobs.py:_run_with_timeout` | Bounded and reported, not solved. A process-based worker would actually fix it. |
| `/api/jobs` and `/{id}/status` | `routes_jobs.py` | Unused by the UI; `/status` is a documented alias. Could be removed in a major version. |
| No component tests | `frontend/` | Unit tests cover `lib/` and the markdown guards. No React Testing Library setup. |
| `output_size` backfill | `JobFileState.output_size` | New jobs record it; pre-existing jobs still fall back to walking the directory. |
| Retention `_cleanup_loop` per worker | `app/main.py` | Would run in every uvicorn worker under a multi-worker deploy. Latent — Docker runs one worker. |
| Redis/worker health probes | `routes_health.py` | Only meaningful in celery mode; unverified. |

### Suggested next steps

1. **Commit this work.** It is a large uncommitted change (50 files). Suggested split:
   Docker fix → format expansion + local-only containment → image extraction →
   search → SSE → upload progress → hardening/cleanup.
2. Decide on `.claude/launch.json` (added for dev-server convenience; untracked).
3. If Celery mode matters, it needs tests — it is the largest untested surface.

---

## 7. Environment notes

- Backend venv: `backend/.venv` (Python 3.12). `pyproject.toml` requires ≥3.11;
  CI and Docker use 3.13. README now says 3.11+.
- Playwright Chromium was installed this session (`~/.cache/ms-playwright`, ~115 MB).
- `vitest` + `jsdom` were added as frontend dev dependencies.
- `frontend/e2e/fixtures/*` are **regenerated on every e2e run** by
  `globalSetup`. Revert them (`git checkout -- frontend/e2e/fixtures/`) before
  committing, or they add binary churn to every diff.
- `storage/` on this machine contains the user's real personal documents. It is
  gitignored; do not commit it or copy it into a worktree.

## 8. New/changed files worth reading first

```
backend/converters/images.py            image extraction + noise filter    (new)
backend/converters/markitdown.py        build_local_engine(), _attach_images
backend/app/services/search.py          FTS5 index                          (new)
backend/app/core/config.py              data_dir derivation, max_file_mb
backend/app/core/db.py                  migration runner
backend/app/api/routes_jobs.py          SSE, assets route, HEAD support
frontend/lib/api.ts                     XHR upload, streaming download
frontend/lib/unsaved.ts                 nav guard registry                  (new)
frontend/components/ui/tabs.tsx         full ARIA tabs pattern
frontend/playwright.global-setup.ts     the data-dir race fix — read §5.1
```
