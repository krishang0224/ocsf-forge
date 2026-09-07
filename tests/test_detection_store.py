from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from ulpf.detection.config import DetectionSettings
from ulpf.detection.models import AuthenticationEvent
from ulpf.detection.rules import evaluate
from ulpf.detection.store import DETECTION_COLUMNS, DetectionStore
from ulpf.detection.worker import run_once

START = datetime(2026, 9, 7, 12, tzinfo=UTC)
END = START + timedelta(hours=1)


class RecordingStore(DetectionStore):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.rows = []
        self.saved = set()
        self.fail_write = False

    @contextmanager
    def _connection(self):
        yield object()

    def _execute_on_connection(self, connection, statement, params=None, row_limit=None):
        self.calls.append((statement, params, row_limit))
        if statement.startswith("SELECT"):
            return [], self.rows
        if statement.startswith("MERGE"):
            if self.fail_write:
                self.fail_write = False
                raise ConnectionError("storage unavailable")
            self.saved.update(params[::len(DETECTION_COLUMNS)])
        return [], []


def source_rows():
    return [[f"e{i}", START + timedelta(seconds=i), "host", "service", "192.0.2.1", "alice", 2] for i in range(5)]


def test_scan_is_bounded_and_filters_authentication_logons():
    store = RecordingStore()
    store.read_authentication(START, END, 100)
    statement, params, limit = store.calls[0]
    assert params == [START, END]
    assert limit == 101 and "LIMIT 101" in statement
    assert "class_uid = 3002" in statement and "activity_id = 1" in statement


def test_overflow_fails_before_writing_findings():
    store = RecordingStore()
    store.rows = source_rows()
    with pytest.raises(ValueError, match="max_events"):
        run_once(store, DetectionSettings(max_events=4), start=START, end=END)
    assert not store.saved
    assert len(store.calls) == 1


def test_failed_write_can_be_replayed_without_changing_finding_id():
    store = RecordingStore()
    store.rows = source_rows()
    store.fail_write = True
    with pytest.raises(ConnectionError):
        run_once(store, DetectionSettings(), start=START, end=END)
    result = run_once(store, DetectionSettings(), start=START, end=END)
    assert result["findings_matched"] == 1
    original = store.saved.copy()
    run_once(store, DetectionSettings(), start=START, end=END)
    assert store.saved == original
    assert len(store.saved) == 1


def test_finding_writes_bind_values_and_deduplicate_within_batch():
    store = RecordingStore()
    events = [AuthenticationEvent(*row) for row in source_rows()]
    finding = evaluate(events, START, END)[0]
    store.write_findings([finding, finding])
    statement, params, _ = store.calls[0]
    assert "WHEN NOT MATCHED THEN INSERT" in statement
    assert "WHEN MATCHED" not in statement
    assert finding.event_id not in statement
    assert len(params) == len(DETECTION_COLUMNS)


def test_scan_reads_preceding_window_as_context():
    store = RecordingStore()
    run_once(store, DetectionSettings(), start=START, end=END)
    assert store.calls[0][1] == [START - timedelta(seconds=300), END]


def test_worker_health_requires_recent_successful_scan(monkeypatch, tmp_path):
    from ulpf.detection import worker

    heartbeat = tmp_path / "heartbeat"
    monkeypatch.setattr(worker, "HEARTBEAT", heartbeat)
    monkeypatch.setattr(worker, "time", lambda: 1000)
    assert not worker.healthy(DetectionSettings())
    heartbeat.write_text("999")
    assert worker.healthy(DetectionSettings())
    heartbeat.write_text("0")
    assert not worker.healthy(DetectionSettings())
    heartbeat.write_text("invalid")
    assert not worker.healthy(DetectionSettings())
