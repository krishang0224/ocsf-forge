"""Trino gateway for safe queries and recoverable Iceberg ingestion."""

import json
import logging
import random
import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter, sleep
from typing import TypeVar

import pandas as pd
from trino.dbapi import connect

from ulpf.config import Settings, settings
from ulpf.models import IngestionResult, NormalizedEvent
from ulpf.services.backend import QueryBackend, UnsafeQueryError
from ulpf.services.sql_guard import scrub_sql
from ulpf.sql import LAKEHOUSE_SETUP

READ_ONLY_PREFIXES = {"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH", "TABLE", "VALUES"}
BLOCKED_MULTI_STATEMENT = re.compile(r";\s*\S")
MUTATING_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|CALL|GRANT|REVOKE|SET|RESET|USE)\b",
    re.IGNORECASE,
)
COMMIT_CONFLICT_MARKERS = ("ICEBERG_COMMIT_ERROR", "TRANSACTION_CONFLICT")
LOGGER = logging.getLogger(__name__)
MergeItem = TypeVar("MergeItem")


class TrinoService(QueryBackend):
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

    def execute(
        self,
        statement: str,
        params: list | tuple | None = None,
        row_limit: int | None = None,
    ) -> tuple[list[str], list[list]]:
        with self._connection() as connection:
            return self._execute_on_connection(connection, statement, params, row_limit)

    @staticmethod
    def _execute_on_connection(
        connection,
        statement: str,
        params: list | tuple | None = None,
        row_limit: int | None = None,
    ):
        cursor = connection.cursor()
        try:
            cursor.execute(statement, params)
            rows = cursor.fetchmany(row_limit) if row_limit is not None else cursor.fetchall()
            columns = [column[0] for column in cursor.description] if cursor.description else []
            return columns, rows
        finally:
            try:
                cursor.close()
            except Exception:
                LOGGER.warning("Failed to close Trino cursor", exc_info=True)

    def query(self, statement: str, enforce_read_only: bool = True) -> tuple[pd.DataFrame, float]:
        sql = statement.strip()
        if not sql:
            raise ValueError("Enter a SQL statement.")
        scrubbed = scrub_sql(sql).strip()
        if not scrubbed or not scrubbed.strip(";").strip():
            raise ValueError("Enter a SQL statement.")
        if BLOCKED_MULTI_STATEMENT.search(scrubbed.rstrip(";")):
            raise UnsafeQueryError("Run one SQL statement at a time.")
        first_keyword = scrubbed.split(maxsplit=1)[0].upper()
        is_read_only = first_keyword in READ_ONLY_PREFIXES and not MUTATING_KEYWORDS.search(scrubbed)
        if enforce_read_only and not self.config.allow_mutating_sql and not is_read_only:
            raise UnsafeQueryError("This console is read-only. Set ULPF_ALLOW_MUTATING_SQL=true to enable DDL and DML.")
        started = perf_counter()
        columns, rows = self.execute(sql, row_limit=self.config.query_row_limit)
        elapsed = perf_counter() - started
        if columns:
            return pd.DataFrame(rows, columns=columns), elapsed
        return pd.DataFrame({"status": ["Statement completed"]}), elapsed

    def query_many(self, statements: dict[str, str]) -> dict[str, pd.DataFrame]:
        results: dict[str, pd.DataFrame] = {}
        with self._connection() as connection:
            for name, statement in statements.items():
                columns, rows = self._execute_on_connection(
                    connection, statement, row_limit=self.config.query_row_limit
                )
                results[name] = pd.DataFrame(rows, columns=columns)
        return results

    def insert_events(self, events: Iterable[NormalizedEvent]) -> int:
        """Compatibility wrapper returning newly committed normalized rows."""
        return self.ingest_events(events).committed

    def ingest_events(self, events: Iterable[NormalizedEvent]) -> IngestionResult:
        received_items = list(events)
        if not received_items:
            return IngestionResult("", 0, 0, 0, 0, "EMPTY")
        items = list({event.event_id: event for event in received_items}.values())
        input_duplicates = len(received_items) - len(items)
        run_id = str(uuid.uuid4())
        items = [replace(event, ingestion_run_id=run_id) for event in items]
        started_at = datetime.now(UTC)
        source_ids = {event.source_id for event in items}
        source_names = {event.source_name or "interactive" for event in items}
        source_id = next(iter(source_ids)) if len(source_ids) == 1 else "multiple"
        source_name = next(iter(source_names)) if len(source_names) == 1 else "multiple"
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
            len(received_items),
            sum(event.parse_success for event in received_items),
            sum(not event.parse_success for event in received_items),
            0,
            0,
            None,
            "",
        )
        try:
            with self._connection() as connection:
                self._insert_run(connection, initial)
                valid = [event for event in items if event.parse_success]
                invalid = [event for event in items if not event.parse_success]
                self._assert_events_fit("iceberg.logging.raw_events", self.raw_columns(), items, self._raw_values)
                self._assert_events_fit(
                    self.config.qualified_table, self.normalized_columns(), valid, self._event_values
                )
                self._assert_events_fit(
                    "iceberg.logging.quarantine_events",
                    self.quarantine_columns(),
                    invalid,
                    self._quarantine_values,
                )
                self._merge_batches(
                    connection, "iceberg.logging.raw_events", self.raw_columns(), items, self._raw_values
                )
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
                duplicates = input_duplicates + len(items) - committed - quarantined
                _, snapshot_rows = self._execute_on_connection(
                    connection,
                    'SELECT snapshot_id FROM iceberg.logging."application_logs$snapshots" ORDER BY committed_at DESC LIMIT 1',
                )
                snapshot_id = snapshot_rows[0][0] if snapshot_rows else None
                status = "COMPLETED_WITH_QUARANTINE" if quarantined else "COMPLETED"
                self._finish_run(connection, run_id, status, committed, quarantined, duplicates, snapshot_id, "")
            return IngestionResult(run_id, len(received_items), committed, quarantined, duplicates, status)
        except Exception as exc:
            try:
                with self._connection() as connection:
                    self._finish_run(connection, run_id, "FAILED", 0, 0, 0, None, str(exc)[:2000])
            except Exception:
                LOGGER.exception("Failed to record failed ingestion run %s", run_id)
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
        events: list[MergeItem],
        values: Callable[[MergeItem], tuple],
    ) -> None:
        value_group = "(" + ", ".join("?" for _ in columns) + ")"
        aliases = ", ".join(columns)
        inserts = ", ".join(f"source.{column}" for column in columns)
        fixed_size = len(table) + len(aliases) * 2 + len(inserts) + 256
        batch: list[tuple] = []
        estimated_size = fixed_size
        for event in events:
            event_values = values(event)
            event_size = len(value_group) + sum(self._prepared_value_size(value) + 1 for value in event_values)
            if event_size + fixed_size > self.config.trino_max_query_bytes:
                raise ValueError(
                    "A single event is too large for safe Trino parameter binding; "
                    "reduce the record size or store its payload externally."
                )
            if batch and (
                len(batch) >= self.config.insert_batch_size
                or estimated_size + event_size > self.config.trino_max_query_bytes
            ):
                self._merge_batch(connection, table, columns, batch, aliases, inserts, value_group)
                batch = []
                estimated_size = fixed_size
            batch.append(event_values)
            estimated_size += event_size
        if batch:
            self._merge_batch(connection, table, columns, batch, aliases, inserts, value_group)

    def _assert_events_fit(self, table, columns, events, values) -> None:
        value_group_size = len(columns) * 3 + 2
        fixed_size = len(table) + len(", ".join(columns)) * 2 + 512
        for event in events:
            event_size = value_group_size + sum(
                self._prepared_value_size(value) + 1 for value in values(event)
            )
            if event_size + fixed_size > self.config.trino_max_query_bytes:
                raise ValueError(
                    "A single event is too large for safe Trino parameter binding; "
                    "reduce the record size or store its payload externally."
                )

    def _merge_batch(self, connection, table, columns, batch, aliases, inserts, value_group) -> None:
        params = [value for event_values in batch for value in event_values]
        source_values = ", ".join(value_group for _ in batch)
        statement = (
            f"MERGE INTO {table} AS target USING (VALUES {source_values}) AS source ({aliases}) "
            "ON target.event_id = source.event_id "
            f"WHEN NOT MATCHED THEN INSERT ({aliases}) VALUES ({inserts})"
        )
        self._execute_write_on_connection(connection, statement, params)

    @staticmethod
    def _prepared_value_size(value) -> int:
        """Conservatively estimate trino-python-client's EXECUTE IMMEDIATE text."""
        if value is None:
            return 4
        if isinstance(value, str):
            return len(value.encode("utf-8")) + value.count("'") + 2
        if isinstance(value, datetime):
            return 48
        return len(str(value).encode("utf-8")) + 12

    def _execute_write_on_connection(self, connection, statement, params=None):
        for attempt in range(self.config.iceberg_commit_retries + 1):
            try:
                return self._execute_on_connection(connection, statement, params)
            except Exception as exc:
                if not any(marker in str(exc) for marker in COMMIT_CONFLICT_MARKERS):
                    raise
                if attempt >= self.config.iceberg_commit_retries:
                    raise
                delay = min(0.2 * (2**attempt), 3.0) + random.uniform(0.0, 0.2)
                LOGGER.warning("Iceberg commit conflict; retrying in %.2fs", delay)
                sleep(delay)

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
        aliases = ", ".join(columns)
        inserts = ", ".join(f"source.{column}" for column in columns)
        statement = (
            f"MERGE INTO iceberg.logging.ingestion_runs AS target "
            f"USING (VALUES ({', '.join('?' for _ in columns)})) AS source ({aliases}) "
            "ON target.run_id = source.run_id "
            f"WHEN NOT MATCHED THEN INSERT ({aliases}) VALUES ({inserts})"
        )
        self._execute_write_on_connection(connection, statement, values)

    def _finish_run(self, connection, run_id, status, committed, quarantined, duplicates, snapshot_id, error) -> None:
        self._execute_write_on_connection(
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
