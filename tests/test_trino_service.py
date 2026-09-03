from dataclasses import replace

import pytest

from ulpf.config import settings
from ulpf.models import NormalizedEvent
from ulpf.services.trino import TrinoService, UnsafeQueryError


class RecordingTrino(TrinoService):
    def __init__(self, config=settings):
        super().__init__(config)
        self.calls = []

    def ensure_lakehouse(self):
        return None

    def execute(self, statement, params=None):
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
