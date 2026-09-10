"""Single-process local storage with atomic batches and a read-only SQL surface."""

from __future__ import annotations

import logging
import re
import threading
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from itertools import chain
from pathlib import Path
from time import perf_counter
from typing import Any

import duckdb
import pandas as pd

from ulpf.config import Settings, settings
from ulpf.models import IngestionResult, NormalizedEvent
from ulpf.services.backend import QueryBackend, UnsafeQueryError
from ulpf.services.duckdb_records import normalized_record, quarantine_record, raw_record
from ulpf.services.duckdb_sql import READ_ADAPTATIONS, SETUP
from ulpf.services.sql_guard import scrub_sql
from ulpf.sql import WAREHOUSE_QUERY

_LOCKS: dict[Path, threading.RLock] = {}
LOGGER = logging.getLogger(__name__)
_LOCKS_GUARD = threading.Lock()
_MUTATION = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|CALL|GRANT|REVOKE|SET|RESET|USE|"
    r"ATTACH|DETACH|COPY|EXPORT|IMPORT|INSTALL|LOAD|PRAGMA|VACUUM|CHECKPOINT)\b", re.IGNORECASE,
)


class DuckDBBackend(QueryBackend):
    def __init__(self, config: Settings = settings) -> None:
        if config.backend != "duckdb":
            raise ValueError("DuckDB requires explicit ULPF_BACKEND=duckdb")
        self.config = config
        self.directory = Path(config.homelab_directory).expanduser().resolve()
        self.path = self.directory / "iceberg.duckdb"
        with _LOCKS_GUARD:
            self._lock = _LOCKS.setdefault(self.path, threading.RLock())

    @contextmanager
    def _connection(self, *, read_only: bool = True) -> Iterator[duckdb.DuckDBPyConnection]:
        with self._lock:
            connection = duckdb.connect(str(self.path), read_only=read_only, config={
                "enable_external_access": False, "allow_community_extensions": False,
                "autoinstall_known_extensions": False, "autoload_known_extensions": False,
                "memory_limit": self.config.duckdb_memory_limit, "threads": self.config.duckdb_threads,
            })
            try:
                connection.execute("LOAD icu")
                connection.execute("SET TimeZone='UTC'")
                if self._has_schema(connection):
                    connection.execute("SET schema='logging'")
                yield connection
            finally:
                connection.close()

    @staticmethod
    def _has_schema(connection: duckdb.DuckDBPyConnection) -> bool:
        return bool(connection.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name='logging'").fetchone())

    def ensure_lakehouse(self) -> None:
        """Compatibility name: create local tables, never a lakehouse service."""
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._connection(read_only=False) as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                for statement in SETUP:
                    connection.execute(statement)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def health(self) -> tuple[bool, str]:
        try:
            self.execute("SELECT 1 FROM iceberg.logging.application_logs LIMIT 1")
            return True, "Local DuckDB ready"
        except Exception as exc:
            return False, str(exc)

    def _read(
        self, connection: duckdb.DuckDBPyConnection, statement: str,
        params: list | tuple | None = None, row_limit: int | None = None,
    ) -> tuple[list[str], list[list]]:
        statement = READ_ADAPTATIONS.get(statement.strip().rstrip(";"), statement)
        if len(statement.encode()) > self.config.trino_max_query_bytes:
            raise UnsafeQueryError("SQL statement exceeds the console size limit")
        scrubbed = scrub_sql(statement).strip()
        if not scrubbed or not scrubbed.strip(";").strip():
            raise ValueError("Enter a SQL statement.")
        if _MUTATION.search(scrubbed):
            raise UnsafeQueryError("Homelab SQL is read-only; administrative and mutating statements are disabled")
        statements = connection.extract_statements(statement)
        if len(statements) != 1 or statements[0].type not in {duckdb.StatementType.SELECT, duckdb.StatementType.EXPLAIN}:
            raise UnsafeQueryError("Run one read-only SQL statement at a time")
        limit = self.config.query_row_limit if row_limit is None else min(row_limit, self.config.query_row_limit)
        if limit <= 0:
            raise ValueError("row_limit must be positive")
        timer = threading.Timer(self.config.duckdb_query_timeout, connection.interrupt)
        timer.daemon = True
        timer.start()
        try:
            result = connection.execute(statement, params)
            columns = [column[0] for column in result.description]
            return columns, [list(row) for row in result.fetchmany(limit)]
        finally:
            timer.cancel()
            timer.join()

    def execute(
        self, statement: str, params: list | tuple | None = None, row_limit: int | None = None,
    ) -> tuple[list[str], list[list]]:
        with self._connection() as connection:
            return self._read(connection, statement, params, row_limit)

    def _storage_metrics(self) -> pd.DataFrame:
        with self._lock:
            wal = Path(str(self.path) + ".wal")
            return pd.DataFrame([{
                "database_bytes": self.path.stat().st_size if self.path.exists() else 0,
                "wal_bytes": wal.stat().st_size if wal.exists() else 0,
                "data_files": None, "average_file_mb": None, "snapshots": None,
            }])

    def query(self, statement: str, enforce_read_only: bool = True) -> tuple[pd.DataFrame, float]:
        """Always read-only, including when the Trino-only bypass flag is false."""
        started = perf_counter()
        if statement.strip().rstrip(";") == WAREHOUSE_QUERY:
            frame = self._storage_metrics()
        else:
            columns, rows = self.execute(statement)
            frame = pd.DataFrame(rows, columns=columns)
        return frame, perf_counter() - started

    def query_many(self, statements: dict[str, str]) -> dict[str, pd.DataFrame]:
        results = {}
        with self._connection() as connection:
            connection.execute("BEGIN TRANSACTION")
            for name, statement in statements.items():
                if statement.strip().rstrip(";") == WAREHOUSE_QUERY:
                    results[name] = self._storage_metrics()
                else:
                    columns, rows = self._read(connection, statement)
                    results[name] = pd.DataFrame(rows, columns=columns)
            connection.execute("COMMIT")
        return results

    def _insert_records(
        self, connection: duckdb.DuckDBPyConnection, table: str, records: Iterable[dict[str, Any]],
    ) -> None:
        iterator = iter(records)
        first = next(iterator, None)
        if first is None:
            return
        columns = tuple(first)
        prefix = f"INSERT INTO iceberg.logging.{table} ({', '.join(columns)}) VALUES "
        group = f"({', '.join('?' for _ in columns)})"
        batch: list[tuple] = []

        def flush() -> None:
            sql = prefix + ", ".join(group for _ in batch) + " ON CONFLICT DO NOTHING"
            connection.execute(sql, [value for row in batch for value in row])
            batch.clear()

        for record in chain([first], iterator):
            batch.append(tuple(record[name] for name in columns))
            if len(batch) >= self.config.insert_batch_size:
                flush()
        if batch:
            flush()

    def insert_events(self, events: Iterable[NormalizedEvent]) -> int:
        return self.ingest_events(events).committed

    def ingest_events(self, events: Iterable[NormalizedEvent]) -> IngestionResult:
        received = list(events)
        if not received:
            return IngestionResult("", 0, 0, 0, 0, "EMPTY")
        if any(not event.event_id for event in received):
            raise ValueError("Every event requires a deterministic event_id")
        run_id = str(uuid.uuid4())
        items = [replace(event, ingestion_run_id=run_id) for event in {event.event_id: event for event in received}.values()]

        def shared(values: set[str]) -> str:
            return next(iter(values)) if len(values) == 1 else "multiple"

        run = {
            "run_id": run_id, "source_id": shared({event.source_id for event in items}),
            "source_name": shared({event.source_name or "interactive" for event in items}),
            "source_type": items[0].source_format if len({event.source_format for event in items}) == 1 else "mixed",
            "started_at": datetime.now(UTC),
            "completed_at": None, "status": "RUNNING", "received_count": len(received),
            "parsed_count": sum(event.parse_success for event in received),
            "quarantined_count": 0, "committed_count": 0, "duplicate_count": 0, "snapshot_id": None, "error_message": "",
        }
        with self._connection(read_only=False) as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                self._insert_records(connection, "raw_events", map(raw_record, items))
                self._insert_records(connection, "application_logs", (normalized_record(e) for e in items if e.parse_success))
                self._insert_records(connection, "quarantine_events", (quarantine_record(e) for e in items if not e.parse_success))
                committed = connection.execute("SELECT count(*) FROM logging.application_logs WHERE ingestion_run_id=?", [run_id]).fetchone()[0]
                quarantined = connection.execute("SELECT count(*) FROM logging.quarantine_events WHERE ingestion_run_id=?", [run_id]).fetchone()[0]
                duplicates = len(received) - committed - quarantined
                status = "COMPLETED_WITH_QUARANTINE" if quarantined else "COMPLETED"
                run.update(completed_at=datetime.now(UTC), status=status, committed_count=committed,
                           quarantined_count=quarantined, duplicate_count=duplicates)
                self._insert_records(connection, "ingestion_runs", [run])
                connection.execute("COMMIT")
            except Exception as exc:
                connection.execute("ROLLBACK")
                run.update(completed_at=datetime.now(UTC), status="FAILED", error_message=str(exc)[:2000],
                           committed_count=0, quarantined_count=0, duplicate_count=0)
                try:
                    self._insert_records(connection, "ingestion_runs", [run])
                except Exception:
                    LOGGER.exception("Could not record failed local ingestion run %s", run_id)
                raise
        return IngestionResult(run_id, len(received), committed, quarantined, duplicates, status)
