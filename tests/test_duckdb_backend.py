import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ulpf import sql
from ulpf.config import settings
from ulpf.pipeline import run_pipeline
from ulpf.sample_data import SAMPLE_LOGS
from ulpf.services.backend import QueryBackend, UnsafeQueryError
from ulpf.services.duckdb_sql import EXAMPLES

pytestmark = pytest.mark.skipif(importlib.util.find_spec("duckdb") is None, reason="requires requirements-homelab.txt")


@pytest.fixture
def backend(tmp_path):
    from ulpf.services.duckdb_backend import DuckDBBackend

    service = DuckDBBackend(replace(settings, backend="duckdb", homelab_directory=str(tmp_path), insert_batch_size=2))
    service.ensure_lakehouse()
    return service


def test_contract_empty_database_and_queries(backend):
    assert isinstance(backend, QueryBackend)
    assert backend.health()[0]
    queries = {name: getattr(sql, name) for name in (
        "OVERVIEW_QUERY", "RECENT_QUERY", "SEVERITY_QUERY", "SERVICE_QUERY", "QUALITY_QUERY", "RUNS_QUERY", "WAREHOUSE_QUERY",
    )}
    data = backend.query_many(queries)
    assert data["OVERVIEW_QUERY"].iloc[0].to_dict() == {
        "total_events": 0, "high_critical": 0, "unique_source_ips": 0, "parse_rate": 0,
    }
    assert data["WAREHOUSE_QUERY"].iloc[0]["snapshots"] is None
    assert data["WAREHOUSE_QUERY"].iloc[0]["database_bytes"] > 0
    for statement in EXAMPLES.values():
        backend.query(statement)


def test_ingestion_raw_quarantine_and_replay_survive_reopen(backend):
    from ulpf.services.duckdb_backend import DuckDBBackend

    events = run_pipeline([*SAMPLE_LOGS, "not a recognized log"], source_id="fixture")
    result = backend.ingest_events(events + [events[0]])
    assert (result.received, result.committed, result.quarantined, result.duplicates) == (10, 8, 1, 1)
    reopened = DuckDBBackend(backend.config)
    reopened.ensure_lakehouse()
    result = reopened.ingest_events(events)
    assert (result.committed, result.quarantined, result.duplicates) == (0, 0, 9)
    assert reopened.query("SELECT count(*) AS n FROM raw_events")[0].iloc[0]["n"] == 9
    row = reopened.query("SELECT raw_payload, error_code FROM quarantine_events")[0].iloc[0]
    assert row["raw_payload"] == "not a recognized log"
    assert row["error_code"] == "PARSE_OR_VALIDATION_ERROR"
    assert backend.ingest_events([]).status == "EMPTY"


def test_timestamp_and_ocsf_exact_round_trip(backend):
    event = run_pipeline(['{"timestamp":"2026-09-10T12:34:56.123456+05:30","message":"Robert\'); DROP TABLE x;--"}'])[0]
    assert backend.insert_events([event]) == 1
    row = backend.query("SELECT event_timestamp, original_timestamp, timezone_offset, ocsf_json, message FROM application_logs")[0].iloc[0]
    assert row["event_timestamp"].to_pydatetime() == datetime(2026, 9, 10, 7, 4, 56, 123456, tzinfo=UTC)
    assert row["timezone_offset"] == 330
    assert row["original_timestamp"] == event.original_timestamp
    assert json.loads(row["ocsf_json"]) == event.to_ocsf_dict()
    assert row["message"] == event.message


def test_batch_failure_rolls_back_all_event_tables_and_records_failure(backend, monkeypatch):
    original = backend._insert_records

    def fail(connection, table, records):
        if table == "application_logs":
            raise RuntimeError("injected failure")
        return original(connection, table, records)

    monkeypatch.setattr(backend, "_insert_records", fail)
    with pytest.raises(RuntimeError, match="injected failure"):
        backend.ingest_events(run_pipeline(SAMPLE_LOGS))
    for table in ("raw_events", "application_logs", "quarantine_events"):
        assert backend.query(f"SELECT count(*) AS n FROM {table}")[0].iloc[0]["n"] == 0
    assert backend.query("SELECT status FROM ingestion_runs")[0].iloc[0]["status"] == "FAILED"


@pytest.mark.parametrize("statement", [
    "DROP TABLE application_logs", "SELECT 1; DELETE FROM application_logs", "COPY application_logs TO '/tmp/output.csv'",
    "INSTALL httpfs", "LOAD httpfs", "ATTACH '/tmp/other.duckdb' AS other", "SET enable_external_access=true",
    "PRAGMA enable_external_access=true", "EXPLAIN ANALYZE DELETE FROM application_logs", "CREATE TEMP TABLE x AS SELECT 1",
    "WITH x AS (DELETE FROM application_logs RETURNING *) SELECT * FROM x", "SELECT 1; SELECT 2",
])
def test_all_read_entry_points_block_mutation_even_with_trino_bypass(backend, statement):
    backend.config = replace(backend.config, allow_mutating_sql=True)
    for read in (lambda: backend.query(statement, enforce_read_only=False),
                 lambda: backend.execute(statement), lambda: backend.query_many({"attack": statement})):
        with pytest.raises(UnsafeQueryError):
            read()


@pytest.mark.parametrize("expression", ["read_text(?)", "read_blob(?)", "read_csv(?)", "read_parquet(?)"])
def test_sql_cannot_read_files_outside_database(backend, tmp_path, expression):
    secret = tmp_path / "secret.txt"
    secret.write_text("private fixture")
    with pytest.raises(Exception, match="disabled|Permission|permission|external"):
        backend.execute(f"SELECT * FROM {expression}", [str(secret)])


def test_url_file_scan_is_disabled_without_network_access(backend):
    with pytest.raises(Exception, match="disabled|Permission|permission|external"):
        backend.execute("SELECT * FROM read_csv('https://example.invalid/logs.csv')")


def test_literals_comments_and_row_limits(backend):
    assert backend.query("SELECT '; DROP TABLE x' AS message -- harmless")[0].iloc[0]["message"] == "; DROP TABLE x"
    backend.config = replace(backend.config, query_row_limit=3)
    assert len(backend.query("SELECT * FROM range(100)")[0]) == 3
    assert len(backend.execute("SELECT * FROM range(100)", row_limit=100)[1]) == 3
    with pytest.raises(ValueError):
        backend.query("-- only a comment")


def test_query_timeout_releases_connection(backend):
    backend.config = replace(backend.config, duckdb_query_timeout=.02)
    with pytest.raises(Exception, match="Interrupt"):
        backend.query("SELECT sum(a.i*b.i) FROM range(1000000000) a(i), range(1000000000) b(i)")
    assert backend.query("SELECT 1 AS ok")[0].iloc[0]["ok"] == 1


def test_concurrent_sessions_deduplicate_same_source(backend):
    from ulpf.services.duckdb_backend import DuckDBBackend

    events = run_pipeline(SAMPLE_LOGS, source_id="concurrent")
    services = [DuckDBBackend(backend.config) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda service: service.ingest_events(events), services))
    assert sum(result.committed for result in results) == 8
    assert sum(result.duplicates for result in results) == 24


def test_no_implicit_duckdb_activation(tmp_path):
    from ulpf.services.duckdb_backend import DuckDBBackend

    config = replace(settings, backend="trino", homelab_directory=str(tmp_path / "not-created"))
    with pytest.raises(ValueError, match="explicit"):
        DuckDBBackend(config)
    assert not (tmp_path / "not-created").exists()


def test_storage_column_mapping_matches_trino(backend):
    pytest.importorskip("trino")
    from ulpf.services.duckdb_records import normalized_record, quarantine_record, raw_record
    from ulpf.services.trino import TrinoService

    events = run_pipeline([*SAMPLE_LOGS, "invalid"])
    for event in events:
        for columns, values, record in (
            (TrinoService.raw_columns(), TrinoService._raw_values(event), raw_record(event)),
            (TrinoService.quarantine_columns(), TrinoService._quarantine_values(event), quarantine_record(event)),
            (TrinoService.normalized_columns(), TrinoService._event_values(event), normalized_record(event)),
        ):
            expected = dict(zip(columns, values, strict=True))
            expected.pop("ingested_at", None)
            record.pop("ingested_at", None)
            assert record == expected


def test_2500_events_and_replay_fit_default_memory_limit(backend):
    backend.config = replace(backend.config, insert_batch_size=500, duckdb_memory_limit="256MB")
    events = run_pipeline([
        json.dumps({"timestamp": "2026-09-10T00:00:00.123456Z", "message": f"batch-{index}"})
        for index in range(2500)
    ], source_id="bounded-batch")
    assert backend.ingest_events(events).committed == 2500
    assert backend.ingest_events(events).duplicates == 2500


@pytest.mark.parametrize("changes", [
    {"backend": "automatic"}, {"backend": "duckdb", "homelab_directory": ""},
    {"backend": "duckdb", "duckdb_memory_limit": "unlimited"}, {"backend": "duckdb", "duckdb_threads": 0},
    {"backend": "duckdb", "duckdb_query_timeout": float("nan")},
])
def test_homelab_settings_are_validated(changes):
    with pytest.raises(ValueError):
        replace(settings, **changes)
