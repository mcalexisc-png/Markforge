"""Application configuration loaded from environment variables.

Every value can be overridden via ``MARKFORGE_*`` environment variables or a
``.env`` file, which keeps local, LAN and Docker deployments configurable
without code changes.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

_DEFAULT_SECRET = "dev-only-change-me"
_PLACEHOLDER_SECRETS = {"", "changeme", "change-me", "change_me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MARKFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 3001
    log_level: str = "INFO"

    lan_mode: bool = False
    # Extra allowed CORS origins, comma separated. Localhost dev origins are
    # always allowed; this is for reaching the API directly over a LAN.
    cors_origins: str = ""
    lan_password: str = ""

    job_mode: str = "sync"
    redis_url: str = "redis://localhost:6379/0"
    job_timeout: int = 900
    max_concurrent_jobs: int = 2
    worker_concurrency: int = 2

    # Base directory for everything else. When set, the five paths below are
    # derived from it unless a path is overridden explicitly. This is the one
    # knob a container deployment needs: point it at the mounted volume.
    data_dir: str = ""

    storage_dir: str = "storage"
    database_path: str = "storage/markforge.db"
    upload_dir: str = "storage/uploads"
    output_dir: str = "storage/outputs"
    temp_dir: str = "storage/temp"
    retention_period: int = 7
    cleanup_interval: int = 3600

    max_file_size: int = 100 * 1024 * 1024
    # Friendlier alias for max_file_size. When set it wins, so deployments can
    # say "100" instead of counting bytes.
    max_file_mb: int | None = None
    max_files_per_job: int = 25
    secret_key: str = _DEFAULT_SECRET

    @property
    def is_lan(self) -> bool:
        return self.lan_mode

    @property
    def secret_is_default(self) -> bool:
        value = self.secret_key.strip()
        if value in _PLACEHOLDER_SECRETS or value == _DEFAULT_SECRET:
            return True
        return bool("change" in value.lower() or len(value) < 16)

    def _resolve(self, raw: str) -> Path:
        path = Path(raw)
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        return path

    def _path_for(self, field: str, relative_to_data: str) -> Path:
        """Resolve one storage path.

        An explicitly configured value always wins. Otherwise, when
        ``data_dir`` is set the path is derived from it -- which is what keeps
        a container's data on its mounted volume instead of scattering it
        relative to the code.
        """
        if field in self.model_fields_set:
            return self._resolve(getattr(self, field))
        if self.data_dir:
            return self._resolve(self.data_dir) / relative_to_data
        return self._resolve(getattr(self, field))

    @property
    def effective_max_file_size(self) -> int:
        if self.max_file_mb is not None:
            return max(1, self.max_file_mb) * 1024 * 1024
        return self.max_file_size

    def resolve_storage_dir(self) -> Path:
        return self._path_for("storage_dir", "storage")

    def resolve_database_path(self) -> Path:
        return self._path_for("database_path", "markforge.db")

    def resolve_upload_dir(self) -> Path:
        return self._path_for("upload_dir", "uploads")

    def resolve_output_dir(self) -> Path:
        return self._path_for("output_dir", "outputs")

    def resolve_temp_dir(self) -> Path:
        return self._path_for("temp_dir", "temp")

    def cookie_secret(self) -> str:
        """The key used to sign LAN access cookies.

        Prefers an explicitly configured MARKFORGE_SECRET_KEY. Otherwise a
        strong random key is generated once and persisted in the storage
        directory, so every install has a unique secret without any setup.
        """
        if not self.secret_is_default:
            return self.secret_key
        key_file = self.resolve_storage_dir() / ".secret_key"
        try:
            if key_file.exists():
                stored = key_file.read_text(encoding="utf-8").strip()
                if stored:
                    return stored
            key = secrets.token_urlsafe(48)
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_text(key, encoding="utf-8")
            return key
        except OSError:
            if self.lan_password:
                return f"lan-{self.lan_password}"
            return "markforge-local-dev-secret"


settings = Settings()
