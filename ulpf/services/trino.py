"""Thin, testable Trino gateway for queries and Iceberg ingestion."""

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from time import perf_counter

import pandas as pd
from trino.dbapi import connect

from ulpf.config import Settings, settings
from ulpf.models import NormalizedEvent
from ulpf.sql import CREATE_SCHEMA, CREATE_TABLE

READ_ONLY_PREFIXES = {"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH", "TABLE", "VALUES"}
BLOCKED_MULTI_STATEMENT = re.compile(r";\s*\S")
MUTATING_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|CALL|GRANT|REVOKE|SET|RESET|USE)\b",
    re.IGNORECASE,
)


class UnsafeQueryError(ValueError):
    pass


class TrinoService:
    def __init__(self, config: Settings = settings):
        self.config = config

    def _connection(self):
        return connect(
            host=self.config.trino_host,
            port=self.config.trino_port,
            user=self.config.trino_user,
            catalog=self.config.trino_catalog,
            schema=self.config.trino_schema,
            http_scheme="http",
            source="ulpf-web",
            request_timeout=self.config.trino_request_timeout,
            max_attempts=1,
        )

    def health(self) -> tuple[bool, str]:
        try:
            frame, _ = self.query("SELECT node_version FROM system.runtime.nodes LIMIT 1", enforce_read_only=False)
            version = str(frame.iloc[0, 0]) if not frame.empty else "ready"
            return True, version
        except Exception as exc:  # health status belongs in the UI, not a crash page
            return False, str(exc)

    def ensure_lakehouse(self) -> None:
        self.execute(CREATE_SCHEMA)
        self.execute(CREATE_TABLE)

    def execute(self, statement: str, params: list | tuple | None = None) -> tuple[list[str], list[list]]:
        with self._connection() as connection:
            cursor = connection.cursor()
            cursor.execute(statement, params)
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description] if cursor.description else []
            return columns, rows

    def query(self, statement: str, enforce_read_only: bool = True) -> tuple[pd.DataFrame, float]:
        sql = statement.strip()
        if not sql:
            raise ValueError("Enter a SQL statement.")
        if BLOCKED_MULTI_STATEMENT.search(sql.rstrip(";")):
            raise UnsafeQueryError("Run one SQL statement at a time.")
        first_keyword = re.sub(r"^\s*(?:--[^\n]*\n|/\*.*?\*/\s*)*", "", sql, flags=re.S).split(maxsplit=1)[0].upper()
        scrubbed = re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
        is_read_only = first_keyword in READ_ONLY_PREFIXES and not MUTATING_KEYWORDS.search(scrubbed)
        if enforce_read_only and not self.config.allow_mutating_sql and not is_read_only:
            raise UnsafeQueryError("This console is read-only. Set ULPF_ALLOW_MUTATING_SQL=true to enable DDL and DML.")
        started = perf_counter()
        columns, rows = self.execute(sql)
        elapsed = perf_counter() - started
        if columns:
            rows = rows[: self.config.query_row_limit]
            return pd.DataFrame(rows, columns=columns), elapsed
        return pd.DataFrame({"status": ["Statement completed"]}), elapsed

    def insert_events(self, events: Iterable[NormalizedEvent]) -> int:
        items = list(events)
        if not items:
            return 0
        self.ensure_lakehouse()
        columns = (
            "event_id",
            "event_timestamp",
            "ingested_at",
            "service_name",
            "log_level",
            "message",
            "user_id",
            "ip_address",
            "dst_ip_address",
            "source_format",
            "ocsf_version",
            "category",
            "category_uid",
            "class_name",
            "class_uid",
            "severity_id",
            "action",
            "disposition",
            "status",
            "hostname",
            "device_vendor",
            "raw_payload_hash",
            "original_raw_payload",
            "parse_success",
            "metadata_json",
        )
        value_group = "(" + ", ".join("?" for _ in columns) + ")"
        total = 0
        for start in range(0, len(items), self.config.insert_batch_size):
            batch = items[start : start + self.config.insert_batch_size]
            params: list = []
            for event in batch:
                params.extend(self._event_values(event))
            sql = f"INSERT INTO {self.config.qualified_table} ({', '.join(columns)}) VALUES " + ", ".join(
                value_group for _ in batch
            )
            self.execute(sql, params)
            total += len(batch)
        return total

    @staticmethod
    def _event_values(event: NormalizedEvent) -> tuple:
        try:
            timestamp = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
        except ValueError:
            timestamp = datetime.now(UTC)
        return (
            event.event_id,
            timestamp,
            datetime.now(UTC),
            event.device_product,
            event.severity,
            event.message,
            event.user,
            event.src_endpoint_ip,
            event.dst_endpoint_ip,
            event.source_format,
            event.ocsf_version,
            event.category,
            event.category_uid,
            event.class_name,
            event.class_uid,
            event.severity_id,
            event.action,
            event.disposition,
            event.status,
            event.hostname,
            event.device_vendor,
            event.raw_payload_hash,
            event.original_raw_payload,
            event.parse_success,
            json.dumps(event.metadata or {}, separators=(",", ":"), default=str),
        )
