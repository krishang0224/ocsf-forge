from contextlib import contextmanager
from dataclasses import replace

import pytest

from ulpf.config import settings
from ulpf.models import NormalizedEvent
from ulpf.services.trino import TrinoService, UnsafeQueryError


class RecordingTrino(TrinoService):
    def __init__(self, config=settings):
        super().__init__(config)
        self.calls = []
        self.connections = 0

    @contextmanager
    def _connection(self):
        self.connections += 1
        yield object()

    def _execute_on_connection(self, connection, statement, params=None):
        self.calls.append((statement, params))
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
    event = NormalizedEvent(event_id="event-1", timestamp="2025-01-01T00:00:00Z", message="Robert'); DROP TABLE x;--")
    assert client.insert_events([event]) == 1
    statement, params = client.calls[0]
    assert "?" in statement
    assert event.message not in statement
    assert event.message in params
    assert client.connections == 1


def test_ingestion_reuses_one_connection_across_batches():
    client = RecordingTrino(replace(settings, insert_batch_size=2))
    events = [NormalizedEvent(event_id=f"event-{index}") for index in range(5)]
    assert client.insert_events(events) == 5
    assert client.connections == 1
    assert len(client.calls) == 3


def test_lakehouse_setup_reuses_one_connection():
    client = RecordingTrino()
    client.ensure_lakehouse()
    assert client.connections == 1
    assert len(client.calls) == 2


def test_query_bundle_reuses_one_connection():
    client = RecordingTrino()
    results = client.query_many({"first": "SELECT 1", "second": "SELECT 2"})
    assert client.connections == 1
    assert set(results) == {"first", "second"}
