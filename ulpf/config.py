"""Environment-backed application configuration."""

import math
import os
import re
from dataclasses import dataclass
from typing import Literal


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
    insert_batch_size: int = int(os.getenv("ULPF_INSERT_BATCH_SIZE", "500"))
    trino_max_query_bytes: int = int(os.getenv("ULPF_TRINO_MAX_QUERY_BYTES", "850000"))
    iceberg_commit_retries: int = int(os.getenv("ULPF_ICEBERG_COMMIT_RETRIES", "6"))
    max_upload_bytes: int = int(os.getenv("ULPF_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    backend: Literal["trino", "duckdb"] = os.getenv("ULPF_BACKEND", "trino")
    homelab_directory: str = os.getenv(
        "ULPF_HOMELAB_DIRECTORY", os.path.expanduser("~/.local/share/ocsf-forge")
    )
    duckdb_memory_limit: str = os.getenv("ULPF_DUCKDB_MEMORY_LIMIT", "256MB")
    duckdb_threads: int = int(os.getenv("ULPF_DUCKDB_THREADS", "2"))
    duckdb_query_timeout: float = float(os.getenv("ULPF_DUCKDB_QUERY_TIMEOUT", "10"))

    def __post_init__(self):
        if self.backend not in {"trino", "duckdb"}:
            raise ValueError("ULPF_BACKEND must be trino or duckdb; no automatic fallback is available")
        if self.backend == "duckdb":
            if not self.homelab_directory.strip():
                raise ValueError("homelab_directory must not be empty")
            if not re.fullmatch(r"[1-9][0-9]*(MB|GB)", self.duckdb_memory_limit):
                raise ValueError("duckdb_memory_limit must be a positive whole number followed by MB or GB")
            if self.duckdb_threads <= 0:
                raise ValueError("duckdb_threads must be positive")
            if not math.isfinite(self.duckdb_query_timeout) or self.duckdb_query_timeout <= 0:
                raise ValueError("duckdb_query_timeout must be finite and positive")
        for name in ("query_row_limit", "insert_batch_size", "trino_max_query_bytes", "max_upload_bytes"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.iceberg_commit_retries < 0:
            raise ValueError("iceberg_commit_retries cannot be negative")
        if not math.isfinite(self.trino_request_timeout) or self.trino_request_timeout <= 0:
            raise ValueError("trino_request_timeout must be finite and positive")
        if not 1 <= self.trino_port <= 65535:
            raise ValueError("trino_port must be between 1 and 65535")
        if self.trino_http_scheme not in {"http", "https"}:
            raise ValueError("trino_http_scheme must be http or https")
        for name in ("trino_catalog", "trino_schema", "trino_table"):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", getattr(self, name)):
                raise ValueError(f"{name} must be a simple SQL identifier")

    @property
    def qualified_table(self) -> str:
        return f"{self.trino_catalog}.{self.trino_schema}.{self.trino_table}"

    @property
    def trino_auth(self):
        if not self.trino_password:
            return None
        from trino.auth import BasicAuthentication

        return BasicAuthentication(self.trino_user, self.trino_password) if self.trino_password else None


settings = Settings()
