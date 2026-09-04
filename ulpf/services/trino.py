"""Trino gateway for safe queries and recoverable Iceberg ingestion."""

import json
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter

import pandas as pd
from trino.dbapi import connect

from ulpf.config import Settings, settings
from ulpf.models import IngestionResult, NormalizedEvent
from ulpf.sql import LAKEHOUSE_SETUP

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
            http_scheme=self.config.trino_http_scheme,
            auth=self.config.trino_auth,
            source="ulpf-web",
            request_timeout=self.config.trino_request_timeout,
            max_attempts=1,
        )

    def health(self) -> tuple[bool, str]:
        try:
            self.query("SELECT 1 AS ready", enforce_read_only=False)
            return True, "ready"
        except Exception as exc:
            return False, str(exc)

    def ensure_lakehouse(self) -> None:
        with self._connection() as connection:
            for statement in LAKEHOUSE_SETUP:
                self._execute_on_connection(connection, statement)

    def execute(self, statement: str, params: list | tuple | None = None) -> tuple[list[str], list[list]]:
        with self._connection() as connection:
            return self._execute_on_connection(connection, statement, params)

    @staticmethod
    def _execute_on_connection(connection, statement: str, params: list | tuple | None = None):
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
            return pd.DataFrame(rows[: self.config.query_row_limit], columns=columns), elapsed
        return pd.DataFrame({"status": ["Statement completed"]}), elapsed

    def query_many(self, statements: dict[str, str]) -> dict[str, pd.DataFrame]:
        results: dict[str, pd.DataFrame] = {}
        with self._connection() as connection:
            for name, statement in statements.items():
                columns, rows = self._execute_on_connection(connection, statement)
                results[name] = pd.DataFrame(rows[: self.config.query_row_limit], columns=columns)
        return results

    def insert_events(self, events: Iterable[NormalizedEvent]) -> int:
        """Compatibility wrapper returning newly committed normalized rows."""
        return self.ingest_events(events).committed

    def ingest_events(self, events: Iterable[NormalizedEvent]) -> IngestionResult:
        items = list(events)
        if not items:
            return IngestionResult("", 0, 0, 0, 0, "EMPTY")
        run_id = str(uuid.uuid4())
        items = [replace(event, ingestion_run_id=run_id) for event in items]
        started_at = datetime.now(UTC)
        source_id = items[0].source_id
        source_name = items[0].source_name or "interactive"
        formats = {event.source_format for event in items}
        source_type = next(iter(formats)) if len(formats) == 1 else "mixed"
        initial = (
            run_id,
            source_id,
            source_name,
            source_type,
            started_at,
            None,
            "RUNNING",
            len(items),
            sum(event.parse_success for event in items),
            sum(not event.parse_success for event in items),
            0,
            0,
            None,
            "",
        )
        try:
            with self._connection() as connection:
                self._insert_run(connection, initial)
                self._merge_batches(
                    connection, "iceberg.logging.raw_events", self.raw_columns(), items, self._raw_values
                )
                valid = [event for event in items if event.parse_success]
                invalid = [event for event in items if not event.parse_success]
                self._merge_batches(
                    connection,
                    self.config.qualified_table,
                    self.normalized_columns(),
                    valid,
                    self._event_values,
                )
                self._merge_batches(
                    connection,
                    "iceberg.logging.quarantine_events",
                    self.quarantine_columns(),
                    invalid,
                    self._quarantine_values,
                )
                committed = self._count_for_run(connection, self.config.qualified_table, run_id)
                quarantined = self._count_for_run(connection, "iceberg.logging.quarantine_events", run_id)
                duplicates = len(items) - committed - quarantined
                _, snapshot_rows = self._execute_on_connection(
                    connection,
                    'SELECT max(snapshot_id) FROM iceberg.logging."application_logs$snapshots"',
                )
                snapshot_id = snapshot_rows[0][0] if snapshot_rows else None
                status = "COMPLETED_WITH_QUARANTINE" if quarantined else "COMPLETED"
                self._finish_run(connection, run_id, status, committed, quarantined, duplicates, snapshot_id, "")
            return IngestionResult(run_id, len(items), committed, quarantined, duplicates, status)
        except Exception as exc:
            try:
                with self._connection() as connection:
                    self._finish_run(connection, run_id, "FAILED", 0, 0, 0, None, str(exc)[:2000])
            except Exception:
                pass
            raise

    @staticmethod
    def raw_columns() -> tuple[str, ...]:
        return (
            "event_id",
            "ingestion_run_id",
            "source_id",
            "source_name",
            "source_type",
            "source_offset",
            "observed_at",
            "raw_payload",
            "raw_payload_hash",
            "parser_name",
            "parser_version",
            "detection_confidence",
            "parse_success",
        )

    @staticmethod
    def normalized_columns() -> tuple[str, ...]:
        return (
            "event_id",
            "ingestion_run_id",
            "event_timestamp",
            "observed_at",
            "ingested_at",
            "original_timestamp",
            "timezone_offset",
            "time_source",
            "service_name",
            "log_level",
            "message",
            "user_id",
            "ip_address",
            "src_port",
            "dst_ip_address",
            "dst_port",
            "source_format",
            "source_id",
            "source_name",
            "source_offset",
            "parser_name",
            "parser_version",
            "ocsf_version",
            "category",
            "category_uid",
            "class_name",
            "class_uid",
            "activity_name",
            "activity_id",
            "type_uid",
            "severity_id",
            "action",
            "disposition",
            "status",
            "status_id",
            "hostname",
            "device_vendor",
            "raw_payload_hash",
            "metadata_json",
            "ocsf_json",
        )

    @staticmethod
    def quarantine_columns() -> tuple[str, ...]:
        return (
            "event_id",
            "ingestion_run_id",
            "source_id",
            "source_name",
            "source_type",
            "source_offset",
            "observed_at",
            "original_timestamp",
            "parser_name",
            "parser_version",
            "error_code",
            "error_message",
            "raw_payload",
            "raw_payload_hash",
            "metadata_json",
        )

    def _merge_batches(
        self,
        connection,
        table: str,
        columns: tuple[str, ...],
        events: list[NormalizedEvent],
        values: Callable[[NormalizedEvent], tuple],
    ) -> None:
        value_group = "(" + ", ".join("?" for _ in columns) + ")"
        for start in range(0, len(events), self.config.insert_batch_size):
            batch = events[start : start + self.config.insert_batch_size]
            params = [value for event in batch for value in values(event)]
            aliases = ", ".join(columns)
            source_values = ", ".join(value_group for _ in batch)
            inserts = ", ".join(f"source.{column}" for column in columns)
            statement = (
                f"MERGE INTO {table} AS target USING (VALUES {source_values}) AS source ({aliases}) "
                "ON target.event_id = source.event_id "
                f"WHEN NOT MATCHED THEN INSERT ({aliases}) VALUES ({inserts})"
            )
            self._execute_on_connection(connection, statement, params)

    def _insert_run(self, connection, values: tuple) -> None:
        columns = (
            "run_id",
            "source_id",
            "source_name",
            "source_type",
            "started_at",
            "completed_at",
            "status",
            "received_count",
            "parsed_count",
            "quarantined_count",
            "committed_count",
            "duplicate_count",
            "snapshot_id",
            "error_message",
        )
        statement = f"INSERT INTO iceberg.logging.ingestion_runs ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
        self._execute_on_connection(connection, statement, values)

    def _finish_run(self, connection, run_id, status, committed, quarantined, duplicates, snapshot_id, error) -> None:
        self._execute_on_connection(
            connection,
            """UPDATE iceberg.logging.ingestion_runs
               SET completed_at = ?, status = ?, committed_count = ?, quarantined_count = ?,
                   duplicate_count = ?, snapshot_id = ?, error_message = ?
               WHERE run_id = ?""",
            (datetime.now(UTC), status, committed, quarantined, duplicates, snapshot_id, error, run_id),
        )

    def _count_for_run(self, connection, table: str, run_id: str) -> int:
        _, rows = self._execute_on_connection(
            connection, f"SELECT count(*) FROM {table} WHERE ingestion_run_id = ?", (run_id,)
        )
        return int(rows[0][0])

    @classmethod
    def _raw_values(cls, event: NormalizedEvent) -> tuple:
        confidence = float((event.metadata or {}).get("detection_confidence", 0.0))
        return (
            event.event_id,
            event.ingestion_run_id,
            event.source_id,
            event.source_name,
            event.source_format,
            event.source_offset,
            cls._datetime(event.observed_at),
            event.original_raw_payload,
            event.raw_payload_hash,
            event.parser_name,
            event.parser_version,
            confidence,
            event.parse_success,
        )

    @classmethod
    def _event_values(cls, event: NormalizedEvent) -> tuple:
        return (
            event.event_id,
            event.ingestion_run_id,
            cls._datetime(event.timestamp),
            cls._datetime(event.observed_at),
            datetime.now(UTC),
            event.original_timestamp,
            event.timezone_offset,
            event.time_source,
            event.device_product,
            event.severity,
            event.message,
            event.user,
            event.src_endpoint_ip,
            event.src_endpoint_port,
            event.dst_endpoint_ip,
            event.dst_endpoint_port,
            event.source_format,
            event.source_id,
            event.source_name,
            event.source_offset,
            event.parser_name,
            event.parser_version,
            event.ocsf_version,
            event.category,
            event.category_uid,
            event.class_name,
            event.class_uid,
            event.activity_name,
            event.activity_id,
            event.type_uid,
            event.severity_id,
            event.action,
            event.disposition,
            event.status,
            event.status_id,
            event.hostname,
            event.device_vendor,
            event.raw_payload_hash,
            json.dumps(event.metadata or {}, separators=(",", ":"), default=str),
            json.dumps(event.to_ocsf_dict(), separators=(",", ":"), default=str),
        )

    @classmethod
    def _quarantine_values(cls, event: NormalizedEvent) -> tuple:
        return (
            event.event_id,
            event.ingestion_run_id,
            event.source_id,
            event.source_name,
            event.source_format,
            event.source_offset,
            cls._datetime(event.observed_at),
            event.original_timestamp,
            event.parser_name,
            event.parser_version,
            "PARSE_OR_VALIDATION_ERROR",
            event.parse_notes,
            event.original_raw_payload,
            event.raw_payload_hash,
            json.dumps(event.metadata or {}, separators=(",", ":"), default=str),
        )

    @staticmethod
    def _datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
