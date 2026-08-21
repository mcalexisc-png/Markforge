"""SQLAlchemy engine/session setup for SQLite (PostgreSQL-ready).

The database URL comes from settings; swapping to PostgreSQL only requires
setting a ``sqlalchemy.url`` compatible environment value.
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger("markforge.db")


class Base(DeclarativeBase):
    pass


def _build_engine_url() -> str:
    path = settings.resolve_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def create_app_engine():
    engine = create_engine(
        _build_engine_url(),
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


engine = create_app_engine()
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


# --------------------------------------------------------------------- #
# Schema migrations
# --------------------------------------------------------------------- #
#
# ``create_all`` only ever CREATEs missing tables; it will not alter an
# existing one. Without a migration path, adding a column to ``jobs`` would
# work on a fresh install and break every existing one at runtime.
#
# Versions are tracked in SQLite's built-in ``PRAGMA user_version``, so this
# needs no extra table and no dependency. To change the schema, append a step:
# never edit or renumber an existing one, because installs that already ran it
# will not run it again.


def _migration_001_uploaded_files_sha256(connection) -> None:
    """Index the dedup lookup performed on every upload."""
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_uploaded_files_sha256 "
        "ON uploaded_files (sha256)"
    )


# (version, description, apply)
MIGRATIONS: list[tuple[int, str, object]] = [
    (1, "index uploaded_files.sha256", _migration_001_uploaded_files_sha256),
]

SCHEMA_VERSION = max((v for v, _, _ in MIGRATIONS), default=0)


def _current_schema_version(connection) -> int:
    return int(connection.exec_driver_sql("PRAGMA user_version").scalar() or 0)


def run_migrations() -> int:
    """Apply pending migrations in order. Returns the resulting version."""
    applied = 0
    with engine.begin() as connection:
        version = _current_schema_version(connection)
        for target, description, apply in sorted(MIGRATIONS, key=lambda m: m[0]):
            if target <= version:
                continue
            logger.info("Applying schema migration %d: %s", target, description)
            apply(connection)
            # PRAGMA does not accept bound parameters; the value is an int
            # from this module's own table, never user input.
            connection.exec_driver_sql(f"PRAGMA user_version = {int(target)}")
            version = target
            applied += 1
    if applied:
        logger.info("Schema migrated to version %d (%d step(s))", version, applied)
    return version


def init_db() -> None:
    from app.models import job  # noqa: F401

    Base.metadata.create_all(bind=engine)
    run_migrations()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
