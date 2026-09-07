import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ulpf.detection.config import DetectionSettings
from ulpf.detection.models import AuthenticationEvent
from ulpf.detection.rules import evaluate
from ulpf.pipeline import run_pipeline

START = datetime(2026, 9, 7, 12, tzinfo=UTC)
END = START + timedelta(hours=1)


def auth(index, *, user="alice", status=2, seconds=None, host="login.example", ip="192.0.2.1"):
    return AuthenticationEvent(
        f"event-{index}", START + timedelta(seconds=index if seconds is None else seconds),
        host, "identity", ip, user, status,
    )


def test_repeated_failures_requires_threshold_and_suppresses_same_bucket():
    assert evaluate([auth(i) for i in range(4)], START, END) == []
    findings = evaluate([auth(i) for i in range(12)], START, END)
    assert [item.rule_id for item in findings] == ["auth.repeated_failures"]
    assert findings[0].event_count == 5
    assert set(findings[0].evidence_ids) == {f"event-{i}" for i in range(5)}


def test_spray_counts_distinct_users_not_attempts():
    findings = evaluate([auth(i, user=f"user-{i}") for i in range(5)], START, END)
    assert [item.rule_id for item in findings] == ["auth.password_spray"]
    assert findings[0].event.user == ""
    assert not any(item.rule_id == "auth.password_spray" for item in evaluate(
        [auth(i, user=f"user-{i % 4}") for i in range(12)], START, END
    ))


def test_success_after_failures_requires_strict_event_order_and_same_subject():
    failures = [auth(i) for i in range(5)]
    findings = evaluate([*failures, auth(10, status=1)], START, END)
    success = next(item for item in findings if item.rule_id == "auth.success_after_failures")
    assert success.event_count == 6
    assert "event-10" in success.evidence_ids
    for login in [auth(10, status=1, seconds=0), auth(10, status=1, user="bob"), auth(10, status=1, ip="192.0.2.2")]:
        assert not any(item.rule_id == "auth.success_after_failures" for item in evaluate(
            [*failures, login], START, END
        ))


def test_equal_timestamps_do_not_imply_success_after_failures():
    findings = evaluate([*[auth(i, seconds=0) for i in range(5)], auth(9, seconds=0, status=1)], START, END)
    assert [item.rule_id for item in findings] == ["auth.repeated_failures"]


def test_sliding_window_crosses_clock_bucket_boundary():
    events = [auth(i, seconds=298 + i) for i in range(5)]
    assert len(evaluate(events, START, END)) == 1
    assert evaluate([auth(i, seconds=i * 100) for i in range(5)], START, END) == []


def test_window_lower_boundary_is_inclusive_and_scan_end_exclusive():
    events = [auth(i, seconds=seconds) for i, seconds in enumerate([0, 10, 20, 30, 300])]
    assert len(evaluate(events, START, END)) == 1
    assert evaluate(events, START, START + timedelta(seconds=300)) == []
    assert evaluate([*events[:4], auth(4, seconds=301)], START, END) == []


@pytest.mark.parametrize("change", [
    {"hostname": "another-host"}, {"service": "another-service"}, {"ip_address": "192.0.2.2"},
])
def test_unrelated_scopes_do_not_combine(change):
    events = [auth(i) for i in range(4)] + [replace(auth(4), **change)]
    assert evaluate(events, START, END) == []


@pytest.mark.parametrize("change", [
    {"class_uid": 2004}, {"activity_id": 2}, {"status_id": 0}, {"hostname": ""},
    {"service": ""}, {"user": " "}, {"ip_address": ""}, {"event_id": ""},
])
def test_ineligible_records_do_not_trigger(change):
    assert evaluate([replace(auth(i), **change) for i in range(6)], START, END) == []


def test_replay_order_duplicate_input_and_overlapping_scans_preserve_id():
    events = [auth(i) for i in range(8)]
    first = evaluate(events, START, END)[0]
    second = evaluate(list(reversed(events)) + events, START, END)[0]
    overlap = evaluate(events, START + timedelta(seconds=6), END)[0]
    assert first.event_id == second.event_id == overlap.event_id
    assert first.evidence_ids == second.evidence_ids


def test_context_before_scan_start_can_trigger_but_cannot_emit_before_start():
    events = [auth(i) for i in range(5)]
    assert len(evaluate(events, START + timedelta(seconds=4), END)) == 1
    assert evaluate(events, START + timedelta(seconds=5), END) == []


def test_new_bucket_and_changed_threshold_produce_distinct_findings():
    events = [auth(i) for i in range(6)] + [auth(i + 300) for i in range(6)]
    assert len(evaluate(events, START, END)) == 2
    first = evaluate(events, START, END)[0]
    changed = evaluate(events, START, END, DetectionSettings(failure_threshold=6))[0]
    assert first.event_id != changed.event_id


def test_finding_export_has_classification_provenance_and_bounded_evidence():
    finding = evaluate([auth(i) for i in range(6)], START, END, DetectionSettings(evidence_limit=3))[0]
    record = finding.to_ocsf_dict()
    assert (record["category_uid"], record["class_uid"], record["type_uid"]) == (2, 2004, 200401)
    assert record["is_alert"] is True
    assert record["finding_info"]["uid"] == finding.event_id == record["metadata"]["uid"]
    assert record["unmapped"]["rule_version"] == "1.0.0"
    assert record["unmapped"]["evidence_truncated"] is True
    assert len(finding.evidence_ids) == 3
    assert "event-4" in finding.evidence_ids


def test_real_json_authentication_mapping_supplies_rule_inputs():
    lines = [json.dumps({
        "timestamp": (START + timedelta(seconds=i)).isoformat(), "event_type": "login_failure",
        "host": "login.example", "service": "identity", "src_ip": "192.0.2.1", "user": "alice",
    }) for i in range(5)]
    normalized = run_pipeline(lines)
    assert all(event.parse_success and event.class_uid == 3002 and event.status_id == 2 for event in normalized)
    events = [AuthenticationEvent(
        event.event_id, datetime.fromisoformat(event.timestamp), event.hostname, event.device_product,
        event.src_endpoint_ip, event.user, event.status_id,
    ) for event in normalized]
    assert len(evaluate(events, START, END)) == 1


@pytest.mark.parametrize("changes", [{"max_events": 0}, {"window_seconds": 0}, {"failure_threshold": 1}, {"lookback_seconds": 1}])
def test_invalid_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        DetectionSettings(**changes)
