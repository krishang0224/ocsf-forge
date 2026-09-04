"""Environment-backed application configuration."""

import os
from dataclasses import dataclass

from trino.auth import BasicAuthentication


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    trino_host: str = os.getenv("TRINO_HOST", "trino")
    trino_port: int = int(os.getenv("TRINO_PORT", "8080"))
    trino_user: str = os.getenv("TRINO_USER", "ulpf")
    trino_read_user: str = os.getenv("TRINO_READ_USER", "ulpf_reader")
    trino_dashboard_user: str = os.getenv("TRINO_DASHBOARD_USER", "ulpf_dashboard")
    trino_catalog: str = os.getenv("TRINO_CATALOG", "iceberg")
    trino_schema: str = os.getenv("TRINO_SCHEMA", "logging")
    trino_table: str = os.getenv("TRINO_TABLE", "application_logs")
    trino_request_timeout: float = float(os.getenv("TRINO_REQUEST_TIMEOUT", "3"))
    trino_http_scheme: str = os.getenv("TRINO_HTTP_SCHEME", "http")
    trino_password: str = os.getenv("TRINO_PASSWORD", "")
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "lakehouse-warehouse")
    allow_mutating_sql: bool = _flag("ULPF_ALLOW_MUTATING_SQL")
    query_row_limit: int = int(os.getenv("ULPF_QUERY_ROW_LIMIT", "1000"))
    insert_batch_size: int = int(os.getenv("ULPF_INSERT_BATCH_SIZE", "250"))
    max_upload_bytes: int = int(os.getenv("ULPF_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))

    @property
    def qualified_table(self) -> str:
        return f"{self.trino_catalog}.{self.trino_schema}.{self.trino_table}"

    @property
    def trino_auth(self):
        return BasicAuthentication(self.trino_user, self.trino_password) if self.trino_password else None


settings = Settings()
