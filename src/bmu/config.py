from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BMU_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bmu:bmu@postgres:5432/bmu"
    database_url_sync: str = "postgresql+psycopg://bmu:bmu@postgres:5432/bmu"

    redis_url: str = "redis://redis:6379/0"
    job_stream: str = "bmu:jobs"
    result_stream: str = "bmu:results"
    job_consumer_group: str = "workers"
    result_consumer_group: str = "recorders"

    secret_key: str = "change-me-32-bytes-min-change-me-32-bytes"
    backup_repo_path: Path = Path("/var/lib/bmu/backups")

    scheduler_tick_seconds: int = 15
    scheduler_advisory_lock_id: int = 0x424D5530  # "BMU0"

    worker_concurrency: int = 8
    worker_connect_timeout: int = 30
    worker_command_timeout: int = 60

    web_host: str = "0.0.0.0"
    web_port: int = 8000

    log_level: str = "INFO"
    log_json: bool = False

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
