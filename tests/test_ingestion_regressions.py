import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ulpf.pipeline import EventProcessor, run_payload, run_pipeline
from ulpf.services.trino import TrinoService
from ulpf.streaming.records import parse_record, publish_dead_letters


def test_pasted_syslog_is_not_xml():
    event = run_payload(b"<134>Jan 15 03:14:22 fw-01 daemon: action=deny src=10.0.0.2")[0]
    assert event.source_format == "syslog"
    assert event.parse_success


def test_json_bom_and_hostname_server():
    event = run_payload('\ufeff{"server":"auth.internal","message":"hello"}'.encode())[0]
    assert event.parse_success
    assert event.hostname == "auth.internal"
    assert not event.dst_endpoint_ip


@pytest.mark.parametrize(("action", "extra", "status", "activity"), [
    ("login", {}, "Unknown", 1),
    ("login", {"outcome": "failed"}, "Failure", 1),
    ("login_success", {}, "Success", 1),
    ("logout", {"status": "success"}, "Success", 2),
])
def test_authentication_requires_an_explicit_outcome(action, extra, status, activity):
    event = run_pipeline([json.dumps({"action": action, **extra})])[0]
    assert event.parse_success
    assert event.class_uid == 3002
    assert event.status == status
    assert event.activity_id == activity


def test_conflicting_authentication_outcomes_are_quarantined():
    event = run_pipeline(['{"action":"login_success","status":"failed"}'])[0]
    assert not event.parse_success


def test_authorization_update_is_not_authentication():
    assert run_pipeline(['{"action":"authorization_update"}'])[0].class_uid == 6003


def test_csv_authentication_headers_are_case_insensitive():
    event = run_payload(b"Action,Status,Server,Service\nlogin,failed,auth.internal,ssh\n", "logs.csv")[0]
    assert event.parse_success
    assert event.status == "Failure"
    assert event.device_product == "ssh"


@pytest.mark.parametrize("field", ["host", "user", "src_port", "message"])
def test_nested_scalar_fields_are_quarantined(field):
    event = run_pipeline([json.dumps({field: ["unexpected"]})])[0]
    assert not event.parse_success
    assert "Expected scalar fields" in event.parse_notes


def test_bad_syslog_date_does_not_abort_batch():
    events = run_pipeline(["Feb 31 12:00:00 host app: bad", "Jan 15 12:00:00 host app: good"])
    assert not events[0].parse_success
    assert events[1].parse_success


def test_syslog_leap_day_skips_non_leap_candidate_years():
    event = run_pipeline(["Feb 29 12:00:00 host app: good"], observed_at=datetime(2024, 3, 1, tzinfo=UTC))[0]
    assert event.parse_success
    assert event.timestamp.startswith("2024-02-29")


@pytest.mark.parametrize("payload", [None, b"", b"  ", b"\xff\x00"])
def test_kafka_poison_records_are_preserved_and_quarantined(payload):
    record = SimpleNamespace(value=payload, timestamp=1700000000000, topic="logs", partition=0, offset=42)
    event = parse_record(EventProcessor(), record)
    assert not event.parse_success
    assert event.source_offset == 42
    assert event.event_id == parse_record(EventProcessor(), record).event_id
    if payload == b"\xff\x00":
        assert base64.b64decode(event.metadata["raw_bytes_base64"]) == payload


def test_dead_letter_acknowledgment_failure_propagates():
    producer = Mock()
    producer.send.return_value.get.side_effect = RuntimeError("delivery failed")
    event = run_pipeline(["invalid log"])[0]
    with pytest.raises(RuntimeError, match="delivery failed"):
        publish_dead_letters(producer, "dead-letters", [event])
    producer.flush.assert_called_once()
    producer.send.return_value.get.assert_called_once_with(timeout=30)


@pytest.mark.parametrize("fails", [False, True])
def test_trino_cursor_is_closed_after_partial_fetch_or_error(fails):
    connection = Mock()
    cursor = connection.cursor.return_value
    cursor.description = [("value",)]
    cursor.fetchmany.return_value = [[1]]
    if fails:
        cursor.execute.side_effect = RuntimeError("query failed")
        cursor.close.side_effect = RuntimeError("cleanup failed")
        with pytest.raises(RuntimeError, match="query failed"):
            TrinoService._execute_on_connection(connection, "SELECT 1", row_limit=1)
    else:
        assert TrinoService._execute_on_connection(connection, "SELECT 1", row_limit=1) == (["value"], [[1]])
    cursor.close.assert_called_once()


def test_preview_bounds_rows_and_defers_exports(monkeypatch):
    from ulpf.ui import ingestion

    events = run_pipeline(['{"message":"preview"}'] * 1001)
    convert = Mock(wraps=ingestion.events_to_frame)
    monkeypatch.setattr(ingestion, "events_to_frame", convert)
    monkeypatch.setattr(ingestion, "st", Mock())
    ingestion.st.button.return_value = False
    ingestion.render_batch_preview(events)
    convert.assert_called_once()
    assert len(convert.call_args.args[0]) == 1000
    ingestion.st.columns.assert_not_called()
