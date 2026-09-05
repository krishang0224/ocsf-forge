import hashlib
from datetime import UTC, datetime

import pytest

from ulpf.normalizer import OCSFNormalizer
from ulpf.pipeline import run_payload, run_pipeline


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
    assert event.category == "Other"


def test_cef_extension_preserves_values_containing_spaces():
    line = "CEF:0|Vendor|Product|1|42|Finding|7|msg=Blocked by policy XYZ src=10.0.0.1 act=Block"
    event = run_pipeline([line])[0]
    assert event.metadata["msg"] == "Blocked by policy XYZ"
    assert event.metadata["src"] == "10.0.0.1"
    assert event.metadata["act"] == "Block"
    assert event.status == "New"
    assert event.status_id == 1
    assert event.type_uid == 200401


def test_cef_header_and_extension_escaping_is_preserved():
    line = r"CEF:0|Vendor\|Division|Product|1|42|Name\|detail|7|msg=value\=kept src=2001:db8::1"
    event = run_pipeline([line])[0]
    assert event.parse_success is True
    assert event.device_vendor == "Vendor|Division"
    assert event.message == "value=kept"
    assert event.src_endpoint_ip == "2001:db8::1"


def test_apache_common_log_format_has_empty_optional_metadata():
    line = '127.0.0.1 - frank [15/Jan/2025:03:19:44 +0000] "GET /health HTTP/1.1" 200 12'
    event = run_pipeline([line])[0]
    assert event.source_format == "apache"
    assert event.metadata["referer"] == ""
    assert event.metadata["user_agent"] == ""


def test_event_ids_are_deterministic_but_source_offsets_are_unique():
    line = '{"timestamp":"2025-01-01T00:00:00Z","message":"same"}'
    first = run_pipeline([line], source_id="file-a")[0]
    retry = run_pipeline([line], source_id="file-a")[0]
    next_offset = run_pipeline([line], source_id="file-a", source_offset_start=1)[0]
    assert first.event_id == retry.event_id
    assert first.event_id != next_offset.event_id


def test_invalid_timestamp_is_not_replaced_with_ingestion_time():
    event = run_pipeline(['{"timestamp":"not-a-time","message":"evidence"}'])[0]
    assert event.timestamp is None
    assert event.parse_success is False
    assert "Invalid source timestamp" in event.parse_notes


@pytest.mark.parametrize(
    ("field", "value", "note"),
    [
        ("src_ip", "999.1.1.1", "Invalid source IP address"),
        ("src_port", 70000, "Invalid source port"),
    ],
)
def test_invalid_network_fields_are_quarantined(field, value, note):
    event = run_pipeline([f'{{"timestamp":"2026-09-04T00:00:00Z","{field}":"{value}","message":"bad"}}'])[0]
    assert event.parse_success is False
    assert note in event.parse_notes


def test_rfc3164_year_is_chosen_nearest_to_observation_time():
    observed = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    event = run_pipeline(["Dec 31 23:59:59 host sshd: login allowed"], observed_at=observed)[0]
    assert event.timestamp.startswith("2025-12-31")


def test_leef_and_rfc5424_are_supported():
    leef = run_pipeline(["LEEF:1.0|IBM|QRadar|1|100|src=10.0.0.1\tsev=8\tmsg=Blocked login"])[0]
    syslog = run_pipeline(["<34>1 2026-09-04T12:00:00Z host app 123 ID47 - login allowed"])[0]
    assert leef.source_format == "leef" and leef.parse_success
    assert leef.message == "Blocked login"
    assert syslog.source_format == "syslog" and syslog.parse_success


def test_multiline_log4j_stack_trace_is_one_event():
    events = run_pipeline(
        [
            "2026-09-04 12:00:00,001 ERROR [worker] com.example.Service: failed",
            "    at com.example.Service.run(Service.java:42)",
            "Caused by: java.lang.IllegalStateException",
        ]
    )
    assert len(events) == 1
    assert "Caused by" in events[0].message
    assert events[0].class_name == "Application Error"
    assert events[0].type_uid == 600801


def test_indented_non_log4j_input_is_not_merged_with_previous_event():
    events = run_pipeline(
        [
            '{"timestamp":"2026-09-04T00:00:00Z","message":"first"}',
            '  {"timestamp":"2026-09-04T00:00:01Z","message":"second"}',
        ]
    )
    assert [event.message for event in events] == ["first", "second"]


def test_complete_multiline_log4j_payload_is_one_event():
    payload = (
        "2026-09-04 12:00:00,001 ERROR [worker] com.example.Service: failed\n"
        "    at com.example.Service.run(Service.java:42)\n"
        "Caused by: java.lang.IllegalStateException"
    )
    event = run_pipeline([payload])[0]
    assert event.source_format == "log4j"
    assert "Caused by" in event.message


def test_ocsf_export_contains_canonical_names_and_required_finding_info():
    event = run_pipeline(["CEF:0|Vendor|Product|1|42|Finding|10|src=10.0.0.1"])[0]
    exported = event.to_ocsf_dict()
    assert exported["metadata"]["version"] == "1.8.0"
    assert exported["severity_id"] == 5
    assert exported["type_name"] == "Detection Finding: Create"
    assert exported["finding_info"]["uid"] == "42"
    assert exported["src_endpoint"]["ip"] == "10.0.0.1"


def test_unknown_ocsf_class_fails_closed():
    event = OCSFNormalizer().normalize(
        "custom event",
        "custom",
        {
            "_parsed": True,
            "timestamp_missing_ok": True,
            "class_uid": 9999,
            "category_uid": 9,
            "activity_id": 1,
            "severity": "Low",
        },
    )
    assert event.parse_success is False
    assert "Unsupported OCSF class UID: 9999" in event.parse_notes


def test_pipeline_accepts_a_text_payload_without_iterating_characters():
    events = run_pipeline(
        '{"timestamp":"2026-09-04T00:00:00Z","message":"one"}\n{"timestamp":"2026-09-04T00:00:01Z","message":"two"}'
    )
    assert [event.message for event in events] == ["one", "two"]


def test_pretty_printed_json_object_is_one_uploaded_event():
    payload = b'{\n  "timestamp": "2026-09-04T00:00:00Z",\n  "message": "pretty"\n}'
    events = run_payload(payload, "event.json")
    assert len(events) == 1
    assert events[0].source_format == "json"
    assert events[0].message == "pretty"


def test_pasted_csv_is_sniffed_without_a_filename_extension():
    payload = b"timestamp,level,message\n2026-09-04T00:00:00Z,WARN,pasted csv\n"
    events = run_payload(payload, "Pasted events")
    assert len(events) == 1
    assert events[0].source_format == "csv"
    assert events[0].message == "pasted csv"


def test_pasted_csv_header_sniffing_is_case_insensitive():
    payload = b"Timestamp,Level,Message\n2026-09-04T00:00:00Z,WARN,pasted csv\n"
    events = run_payload(payload, "Pasted events")
    assert len(events) == 1
    assert events[0].source_format == "csv"
    assert events[0].message == "pasted csv"


def test_repeated_xml_fields_are_preserved():
    payload = b"""<Event><EventData>
      <Data Name="User">alice</Data>
      <Data Name="Group">admin</Data>
      <Data Name="Group">audit</Data>
    </EventData></Event>"""
    event = run_payload(payload, "event.xml")[0]
    assert event.metadata["User"] == "alice"
    assert event.metadata["Group"] == ["admin", "audit"]


def test_leef_custom_separator_honors_escaped_delimiters():
    line = r"LEEF:2.0|IBM|QRadar|1|100|^|msg=Blocked\^then allowed^src=10.0.0.1^sev=8"
    event = run_pipeline([line])[0]
    assert event.source_format == "leef"
    assert event.message == "Blocked^then allowed"
    assert event.src_endpoint_ip == "10.0.0.1"


def test_structured_metadata_keeps_only_unmapped_vendor_fields():
    event = run_pipeline(
        ['{"timestamp":"2026-09-04T00:00:00Z","message":"one","src_ip":"10.0.0.1","vendor_code":"A17"}']
    )[0]
    assert event.metadata["vendor_code"] == "A17"
    assert "message" not in event.metadata
    assert "src_ip" not in event.metadata


@pytest.mark.parametrize(
    ("filename", "payload", "expected_format"),
    [
        (
            "events.json",
            b'[{"timestamp":"2026-09-04T00:00:00Z","message":"json"}]',
            "json",
        ),
        (
            "events.csv",
            b"timestamp,message\n2026-09-04T00:00:00Z,csv\n",
            "csv",
        ),
        (
            "events.xml",
            b"<events><event><timestamp>2026-09-04T00:00:00Z</timestamp><message>xml</message></event></events>",
            "xml",
        ),
    ],
)
def test_structured_file_payloads_are_split_into_events(filename, payload, expected_format):
    events = run_payload(payload, filename)
    assert len(events) == 1
    assert events[0].source_format == expected_format
    assert events[0].parse_success is True
