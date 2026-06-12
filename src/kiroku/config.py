from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KIROKU_", env_file=".env", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://bmu:bmu@postgres:5432/bmu"
    database_url_sync: str = "postgresql+psycopg://bmu:bmu@postgres:5432/bmu"

    redis_url: str = "redis://redis:6379/0"
    job_stream: str = "kiroku:jobs"
    result_stream: str = "kiroku:results"
    job_consumer_group: str = "workers"
    result_consumer_group: str = "recorders"

    # When set, the worker subscribes to kiroku:jobs:<worker_pool> and only
    # processes jobs routed to that pool.  Unset = default pool.
    worker_pool: str | None = None

    @property
    def effective_job_stream(self) -> str:
        """The Redis stream this worker reads from (pool-specific or default)."""
        if self.worker_pool:
            return f"{self.job_stream}:{self.worker_pool}"
        return self.job_stream

    secret_key: str = "change-me-32-bytes-min-change-me-32-bytes"
    backup_repo_path: Path = Path("/var/lib/kiroku/backups")

    scheduler_tick_seconds: int = 15
    scheduler_advisory_lock_id: int = 0x4B49524F  # "KIRO"

    worker_concurrency: int = 8
    worker_connect_timeout: int = 30
    worker_command_timeout: int = 60

    # Recorder will force-close any open batch older than this many seconds.
    # Should exceed the longest expected batch duration (devices × command_timeout / concurrency).
    recorder_batch_timeout: int = 1800

    # Redis stream back-pressure controls.
    # Job stream: specs are small (a few KB each); 10 000 is a generous cap.
    # Result stream: entries carry full config text (can be hundreds of KB each)
    # so the cap must be much tighter. The recorder processes results within
    # seconds of arrival, so a few hundred entries of headroom is ample.
    stream_max_len: int = 10000
    stream_high_water_ratio: float = 0.8
    result_stream_max_len: int = 500

    web_host: str = "0.0.0.0"
    web_port: int = 8000
    web_workers: int = 5

    log_level: str = "INFO"
    log_json: bool = False

    # UI dev locally, override with environment variable
    reload: bool = False

    # CVE scanning (optional). Without a key, NVD allows 1 req/s; with a key, 5/s.
    nvd_api_key: str | None = None

    # Auth / RBAC
    # "none"  – no auth enforced (internal/trusted networks, current default)
    # "dev"   – fake login form; pick operator or admin role locally
    # "oidc"  – full Keycloak OIDC flow (production)
    auth_provider: str = "none"
    root_path: str = ""   # e.g. "/kiroku" when behind nginx; empty for dev
    # Public base URL of this app (used to build the OIDC redirect_uri).
    base_url: str = "http://localhost:8000"
    # Keycloak realm URL, e.g. https://keycloak.example.com/realms/myrealm
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    # Role names configured in Keycloak for this app.
    oidc_admin_role: str = "kiroku-admin"
    oidc_operator_role: str = "kiroku-operator"
    # Dot-path into the JWT claims where the roles list lives.
    # Default is Keycloak realm_access.roles; use e.g. "resource_access.kiroku.roles"
    # for client-scoped roles.
    oidc_role_claim: str = "realm_access.roles"

    @property
    def fernet_key(self) -> bytes:
        # Derive a 32-byte urlsafe key from the configured secret_key.
        import base64
        import hashlib

        digest = hashlib.sha256(self.secret_key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)


@lru_cache
def get_settings() -> Settings:
    return Settings()
