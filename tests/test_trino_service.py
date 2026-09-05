from contextlib import contextmanager
from dataclasses import replace

import pytest

from ulpf.config import settings
from ulpf.pipeline import run_pipeline
from ulpf.services.trino import TrinoService, UnsafeQueryError
from ulpf.sql import LAKEHOUSE_SETUP


class RecordingTrino(TrinoService):
    def __init__(self, config=settings):
        super().__init__(config)
        self.calls = []
        self.connections = 0
        self.counts = {"raw_events": 0, "application_logs": 0, "quarantine_events": 0}

    @contextmanager
    def _connection(self):
        self.connections += 1
        yield object()

    def _execute_on_connection(self, connection, statement, params=None, row_limit=None):
        self.calls.append((statement, params))
        table = next((name for name in self.counts if name in statement), None)
        if statement.startswith("MERGE INTO") and table:
            column_count = {
                "raw_events": len(self.raw_columns()),
                "application_logs": len(self.normalized_columns()),
                "quarantine_events": len(self.quarantine_columns()),
            }[table]
            self.counts[table] += len(params) // column_count
        if statement.startswith("SELECT count(*) FROM"):
            table = next(name for name in self.counts if name in statement)
            return (["count"], [[self.counts[table]]])
        if "max(snapshot_id)" in statement:
            return (["snapshot_id"], [[123]])
        return (["value"], [[1]]) if statement.lstrip().upper().startswith("SELECT") else ([], [])


def test_read_only_console_accepts_select():
    client = RecordingTrino()
    result, _ = client.query("SELECT 1")
    assert result.iloc[0, 0] == 1


@pytest.mark.parametrize(
    "statement",
    [
        "DROP TABLE iceberg.logging.application_logs",
        "WITH removed AS (DELETE FROM x RETURNING *) SELECT * FROM removed",
        "SELECT 1; DELETE FROM x",
    ],
)
def test_read_only_console_blocks_mutation(statement):
    client = RecordingTrino()
    with pytest.raises(UnsafeQueryError):
        client.query(statement)


def test_mutating_console_can_be_enabled():
    client = RecordingTrino(replace(settings, allow_mutating_sql=True))
    result, _ = client.query("CREATE SCHEMA example")
    assert result.iloc[0, 0] == "Statement completed"


def test_ingestion_uses_bound_parameters():
    client = RecordingTrino(replace(settings, insert_batch_size=2))
    event = run_pipeline(
        ['{"timestamp":"2025-01-01T00:00:00Z","message":"Robert\'); DROP TABLE x;--"}'],
        source_id="security-test",
    )[0]
    assert client.insert_events([event]) == 1
    statement, params = next(call for call in client.calls if "MERGE INTO iceberg.logging.application_logs" in call[0])
    assert "?" in statement
    assert event.message not in statement
    assert event.message in params
    assert client.connections == 1


def test_ingestion_reuses_one_connection_across_batches():
    client = RecordingTrino(replace(settings, insert_batch_size=2))
    events = run_pipeline(
        [f'{{"timestamp":"2025-01-01T00:00:00Z","message":"event {index}"}}' for index in range(5)],
        source_id="batch-test",
    )
    assert client.insert_events(events) == 5
    assert client.connections == 1
    normalized_merges = [call for call in client.calls if "MERGE INTO iceberg.logging.application_logs" in call[0]]
    assert len(normalized_merges) == 3


def test_lakehouse_setup_reuses_one_connection():
    client = RecordingTrino()
    client.ensure_lakehouse()
    assert client.connections == 1
    assert len(client.calls) == len(LAKEHOUSE_SETUP)


def test_query_bundle_reuses_one_connection():
    client = RecordingTrino()
    results = client.query_many({"first": "SELECT 1", "second": "SELECT 2"})
    assert client.connections == 1
    assert set(results) == {"first", "second"}


def test_large_batches_are_split_by_estimated_query_text_size():
    client = RecordingTrino(
        replace(settings, insert_batch_size=100, trino_max_query_bytes=12_000)
    )
    events = run_pipeline(
        [f'{{"timestamp":"2025-01-01T00:00:00Z","message":"{index}-' + ('x' * 500) + '"}' for index in range(8)],
        source_id="query-size-test",
    )
    assert client.insert_events(events) == 8
    normalized_merges = [call for call in client.calls if "MERGE INTO iceberg.logging.application_logs" in call[0]]
    assert len(normalized_merges) > 1


def test_iceberg_commit_conflicts_are_retried(monkeypatch):
    class ConflictTrino(RecordingTrino):
        remaining_conflicts = 2

        def _execute_on_connection(self, connection, statement, params=None, row_limit=None):
            if "MERGE INTO iceberg.logging.application_logs" in statement and self.remaining_conflicts:
                self.remaining_conflicts -= 1
                raise RuntimeError("ICEBERG_COMMIT_ERROR: concurrent writer")
            return super()._execute_on_connection(connection, statement, params, row_limit)

    monkeypatch.setattr("ulpf.services.trino.sleep", lambda _seconds: None)
    client = ConflictTrino(replace(settings, iceberg_commit_retries=2))
    events = run_pipeline(['{"timestamp":"2025-01-01T00:00:00Z","message":"retry"}'])
    assert client.insert_events(events) == 1
    assert client.remaining_conflicts == 0


def test_oversized_single_event_fails_before_event_tables_are_written():
    client = RecordingTrino(replace(settings, trino_max_query_bytes=10_000))
    event = run_pipeline(
        ['{"timestamp":"2025-01-01T00:00:00Z","message":"' + ("x" * 20_000) + '"}']
    )[0]
    with pytest.raises(ValueError, match="single event is too large"):
        client.ingest_events([event])
    event_merges = [
        statement
        for statement, _params in client.calls
        if statement.startswith("MERGE INTO") and "ingestion_runs" not in statement
    ]
    assert event_merges == []


def test_duplicate_ids_inside_one_batch_are_removed_before_merge():
    client = RecordingTrino()
    event = run_pipeline(
        ['{"timestamp":"2025-01-01T00:00:00Z","message":"duplicate"}'],
        source_id="duplicate-test",
    )[0]
    result = client.ingest_events([event, event])
    assert result.received == 2
    assert result.committed == 1
    assert result.duplicates == 1
    assert client.counts["raw_events"] == 1
    assert client.counts["application_logs"] == 1
