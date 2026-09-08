import base64
import hashlib
import json
import random
from dataclasses import replace
from datetime import datetime

import pytest

from ulpf.config import settings
from ulpf.normalizer import OCSFNormalizer
from ulpf.pipeline import run_payload, run_pipeline


@pytest.mark.parametrize("payload", [
    b"user,user\nalice,bob\n", b"Host,host\na,b\n", b",message\na,b\n",
    b"host,message\na,b,c\n", b"host,message\na\n", b'host,message\na,"unfinished\n',
])
def test_ambiguous_csv_is_rejected_without_losing_document(payload):
    events = run_payload(payload, "input.csv")
    assert len(events) == 1
    assert not events[0].parse_success
    assert events[0].original_raw_payload.encode() == payload


def test_quoted_csv_newline_and_delimiter_are_valid():
    event = run_payload(b'host,message\na,"hello,\nworld"\n', "input.csv")[0]
    assert event.parse_success
    assert event.message == "hello,\nworld"


@pytest.mark.parametrize("payload", [
    b'{"user":"alice","user":"bob"}', b'{"extra":{"key":1,"key":2}}',
    b'{"value":NaN}', b'{"value":Infinity}', b'{"value":1e400}',
    b'[\n{"user":"alice","user":"bob"}\n]',
])
def test_ambiguous_json_is_rejected(payload):
    events = run_payload(payload)
    assert events and not any(event.parse_success for event in events)


def test_invalid_utf8_retains_original_bytes():
    payload = b'{"message":"\xff"}'
    event = run_payload(payload)[0]
    assert not event.parse_success
    assert base64.b64decode(event.metadata["raw_bytes_base64"]) == payload


@pytest.mark.parametrize("port", [True, False, 1.5, -1, 65536])
def test_noninteger_or_out_of_range_ports_fail(port):
    assert OCSFNormalizer._port(port, "source")[1]


def test_raw_hash_matches_preserved_payload_including_newline():
    event = OCSFNormalizer().normalize("evidence\n", "unknown", {"_parsed": False})
    assert hashlib.sha256(event.original_raw_payload.encode()).hexdigest() == event.raw_payload_hash


def test_naive_observation_is_consistently_treated_as_utc():
    event = run_pipeline(["Jan 01 12:00:00 host app: test"], observed_at=datetime(2026, 1, 1))[0]
    assert event.parse_success


@pytest.mark.parametrize("changes", [
    {"iceberg_commit_retries": -1}, {"insert_batch_size": 0}, {"query_row_limit": -1},
    {"trino_request_timeout": float("nan")}, {"trino_port": 0}, {"trino_table": "events; DROP TABLE x"},
])
def test_invalid_settings_fail_before_any_connection(changes):
    with pytest.raises(ValueError):
        replace(settings, **changes)


def test_generated_malformed_fields_never_abort_a_batch():
    rng = random.Random(42)
    fields = ["timestamp", "message", "user", "host", "severity", "src_port", "dst_ip", "action"]
    values = [None, True, False, -1, 0, 1.5, "", "unknown", [], {}, ["nested"], {"nested": 1}]
    lines = [json.dumps({key: rng.choice(values) for key in rng.sample(fields, 4)}) for _ in range(1000)]
    events = run_pipeline(lines)
    assert len(events) == len(lines)
    for event, line in zip(events, lines, strict=True):
        assert event.original_raw_payload == line
        json.dumps(event.to_ocsf_dict(), allow_nan=False)
