"""Environment-backed application configuration."""

import os
from dataclasses import dataclass


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    trino_host: str = os.getenv("TRINO_HOST", "trino")
    trino_port: int = int(os.getenv("TRINO_PORT", "8080"))
    trino_user: str = os.getenv("TRINO_USER", "ulpf")
    trino_catalog: str = os.getenv("TRINO_CATALOG", "iceberg")
    trino_schema: str = os.getenv("TRINO_SCHEMA", "logging")
    trino_table: str = os.getenv("TRINO_TABLE", "application_logs")
    trino_request_timeout: float = float(os.getenv("TRINO_REQUEST_TIMEOUT", "3"))
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "lakehouse-warehouse")
    allow_mutating_sql: bool = _flag("ULPF_ALLOW_MUTATING_SQL")
    query_row_limit: int = int(os.getenv("ULPF_QUERY_ROW_LIMIT", "1000"))
    insert_batch_size: int = int(os.getenv("ULPF_INSERT_BATCH_SIZE", "250"))

    @property
    def qualified_table(self) -> str:
        return f"{self.trino_catalog}.{self.trino_schema}.{self.trino_table}"


settings = Settings()
