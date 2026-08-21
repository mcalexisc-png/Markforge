"""Full-text search over generated Markdown, backed by SQLite FTS5.

The index is derived data: the Markdown on disk is the source of truth, so the
table can be dropped and rebuilt at any time. That is what
:func:`backfill_missing` does on startup for installs that converted documents
before search existed.

Rows are keyed by ``(job_id, file_id)`` and carry the filename alongside the
content so a query can match either.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from app.core.db import engine

logger = logging.getLogger("markforge.search")

# One bm25 weight per column, in declaration order (job_id, filename,
# content, file_id). A filename hit outranks a body hit; the UNINDEXED
# columns cannot match, so their weights are inert but must be supplied.
_BM25_WEIGHTS = "0.0, 8.0, 1.0, 0.0"
MAX_SNIPPET_TOKENS = 24


def init_index() -> None:
    """Create the FTS5 table. Safe to call on every startup."""
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS markdown_fts USING fts5(
                job_id UNINDEXED,
                filename,
                content,
                file_id UNINDEXED,
                tokenize = 'unicode61 remove_diacritics 2'
            )
            """
        )


def index_document(job_id: str, file_id: str, filename: str, content: str) -> None:
    """Insert or replace one document's entry."""
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM markdown_fts WHERE job_id = :job_id "
                    "AND file_id = :file_id"
                ),
                {"job_id": job_id, "file_id": file_id},
            )
            connection.execute(
                text(
                    "INSERT INTO markdown_fts (job_id, filename, content, file_id) "
                    "VALUES (:job_id, :filename, :content, :file_id)"
                ),
                {
                    "job_id": job_id,
                    "filename": filename,
                    "content": content,
                    "file_id": file_id,
                },
            )
    except Exception:
        # Search is an accessory; never fail a conversion because indexing did.
        logger.exception("Failed to index %s/%s", job_id, file_id)


def remove_job(job_id: str) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM markdown_fts WHERE job_id = :job_id"),
                {"job_id": job_id},
            )
    except Exception:
        logger.exception("Failed to drop search rows for %s", job_id)


def _escape(query: str) -> str:
    """Turn user input into a safe FTS5 MATCH expression.

    Every token is quoted, so FTS5 operators a user happens to type ("AND",
    "*", "NEAR") are treated as literal text rather than syntax -- an unquoted
    stray quote or bare operator otherwise raises and 500s the request.
    """
    tokens = [t for t in query.replace('"', " ").split() if t]
    if not tokens:
        return ""
    # Trailing wildcard on the last token gives prefix matching as you type.
    quoted = [f'"{t}"' for t in tokens[:-1]]
    quoted.append(f'"{tokens[-1]}"*')
    return " ".join(quoted)


def search(query: str, limit: int = 25) -> list[dict]:
    """Return ranked matches with a highlighted snippet."""
    match = _escape(query)
    if not match:
        return []
    sql = text(
        f"""
        SELECT job_id, file_id, filename,
               snippet(markdown_fts, 2, '[', ']', ' … ', {MAX_SNIPPET_TOKENS})
                   AS snippet,
               bm25(markdown_fts, {_BM25_WEIGHTS}) AS rank
        FROM markdown_fts
        WHERE markdown_fts MATCH :match
        ORDER BY rank
        LIMIT :limit
        """  # noqa: S608 - only literal constants are interpolated
    )
    try:
        with engine.connect() as connection:
            rows = connection.execute(sql, {"match": match, "limit": limit}).all()
    except Exception:
        # A malformed MATCH expression should read as "no results", not a 500.
        logger.exception("Search failed for %r", query)
        return []
    return [
        {
            "job_id": row.job_id,
            "file_id": row.file_id,
            "filename": row.filename,
            "snippet": row.snippet,
        }
        for row in rows
    ]


def indexed_keys() -> set[tuple[str, str]]:
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT job_id, file_id FROM markdown_fts")).all()
    return {(row.job_id, row.file_id) for row in rows}


def backfill_missing() -> int:
    """Index completed results that predate the search feature."""
    import json

    from app.core.db import SessionLocal
    from app.models.job import Job

    indexed = indexed_keys()
    added = 0
    db = SessionLocal()
    try:
        for job in db.query(Job).filter(Job.status.in_(("completed", "partial"))).all():
            try:
                items = json.loads(job.items_json or "[]")
            except json.JSONDecodeError:
                continue
            for item in items:
                file_id = item.get("file_id")
                output_dir = item.get("output_dir")
                if not file_id or not output_dir:
                    continue
                if (job.id, file_id) in indexed:
                    continue
                path = Path(output_dir) / (item.get("markdown_filename") or "document.md")
                if not path.exists():
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                index_document(job.id, file_id, item.get("filename", ""), content)
                added += 1
    finally:
        db.close()
    if added:
        logger.info("Search backfill indexed %d existing result(s)", added)
    return added
