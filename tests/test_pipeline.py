import hashlib

import pytest

from ulpf.pipeline import run_pipeline


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('{"timestamp":"2025-01-01T00:00:00Z","severity":"error","message":"boom"}', "json"),
        ('127.0.0.1 - - [15/Jan/2025:03:19:44 +0000] "GET / HTTP/1.1" 200 12 "-" "curl"', "apache"),
        ('127.0.0.1 - frank [15/Jan/2025:03:19:44 +0000] "GET /health HTTP/1.1" 200 12', "apache"),
        ("CEF:0|Vendor|Product|1|42|Finding|9|src=10.0.0.1 act=Block", "cef"),
        ("2025-01-15 03:28:12,105 ERROR [worker] com.example.Service: timed out", "log4j"),
        ("<134>Jan 15 03:14:22 fw-01 daemon: action=deny src=10.0.0.2", "syslog"),
    ],
)
def test_pipeline_detects_and_normalizes(line, expected):
    event = run_pipeline([line])[0]
    assert event.source_format == expected
    assert event.parse_success is True
    assert event.original_raw_payload == line
    assert event.raw_payload_hash == hashlib.sha256(line.encode()).hexdigest()


def test_unknown_line_is_preserved_for_forensics():
    line = "not a known log but still evidence"
    event = run_pipeline([line])[0]
    assert event.parse_success is False
    assert event.original_raw_payload == line
    assert event.category == "Uncategorized"


def test_cef_extension_preserves_values_containing_spaces():
    line = "CEF:0|Vendor|Product|1|42|Finding|7|msg=Blocked by policy XYZ src=10.0.0.1 act=Block"
    event = run_pipeline([line])[0]
    assert event.metadata["msg"] == "Blocked by policy XYZ"
    assert event.metadata["src"] == "10.0.0.1"
    assert event.metadata["act"] == "Block"


def test_apache_common_log_format_has_empty_optional_metadata():
    line = '127.0.0.1 - frank [15/Jan/2025:03:19:44 +0000] "GET /health HTTP/1.1" 200 12'
    event = run_pipeline([line])[0]
    assert event.source_format == "apache"
    assert event.metadata["referer"] == ""
    assert event.metadata["user_agent"] == ""
