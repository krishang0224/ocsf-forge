from datetime import UTC, datetime

import pytest

from ulpf.parsing.security import CefParser, LeefParser, parse_extensions
from ulpf.parsing.text import ApacheParser, Log4jParser, SyslogParser
from ulpf.pipeline import run_pipeline

NOW = datetime(2025, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("parser,raw", [
    (CefParser(), "CEF:0|too|short"),
    (CefParser(), "CEF:bad|V|P|1|id|name|5|msg=x"),
    (LeefParser(), "LEEF:1.0|too|short"),
    (Log4jParser(), "not a log4j line"),
    (ApacheParser(), '192.0.2.1 - - [bad] "GET / HTTP/1.1" nope 12'),
    (SyslogParser(), "not a syslog line"),
])
def test_direct_parsers_reject_malformed_headers(parser, raw):
    assert parser.parse(raw, NOW)["_parsed"] is False


@pytest.mark.parametrize("parser,prefix", [
    (CefParser(), "CEF:"), (LeefParser(), "LEEF:"),
])
def test_security_detectors_require_their_prefix(parser, prefix):
    assert parser.detect("  " + prefix + "0|data") == 1.0
    assert parser.detect("unrelated " + prefix + "0|data") == 0.0


@pytest.mark.parametrize("level,expected", [(0, "Low"), (4, "Medium"), (7, "High"), (9, "Critical"),
                                            ("high", "High"), ("", "Unknown")])
def test_cef_numeric_and_named_severity_with_header_message_fallback(level, expected):
    record = CefParser().parse(f"CEF:0|V|P|1|id|Header message|{level}|", NOW)
    assert record["severity"] == expected
    assert record["message"] == "Header message"
    assert record["timestamp_missing_ok"] is True


@pytest.mark.parametrize("level,expected", [(0, "Low"), (4, "Medium"), (7, "High"), (9, "Critical"),
                                            ("high", "High")])
def test_leef_numeric_and_named_severity_preserves_message_equals(level, expected):
    record = LeefParser().parse(f"LEEF:1.0|V|P|1|id|sev={level}\tmalformed-token\tmsg=a=b c", NOW)
    assert record["severity"] == expected
    assert record["message"] == "a=b c"
    assert "malformed-token" not in record["metadata"]


@pytest.mark.parametrize("suffix", ["", "|"])
def test_leef_absent_extension_has_explicit_defaults(suffix):
    record = LeefParser().parse("LEEF:2.0|V|P|1|id" + suffix, NOW)
    assert record["message"] == "id"
    assert record["severity"] == "Informational"
    assert record["timestamp_missing_ok"] is True


@pytest.mark.parametrize("delimiter,payload", [("^", "sev=4^msg=two words"),
                                              ("0x09", "sev=4\tmsg=two words"),
                                              ("", "sev=4\tmsg=two words")])
def test_leef_v2_delimiters(delimiter, payload):
    record = LeefParser().parse(f"LEEF:2.0|V|P|1|id|{delimiter}|{payload}", NOW)
    assert record["severity"] == "Medium"
    assert record["message"] == "two words"


def test_cef_escaped_equals_does_not_create_a_phantom_extension():
    assert parse_extensions(r"msg=blocked by policy fake\=value src=192.0.2.1") == {
        "msg": "blocked by policy fake=value", "src": "192.0.2.1",
    }
    assert parse_extensions("not an extension") == {}


def test_apache_invalid_date_is_quarantined_not_replaced_with_observation_time():
    line = '192.0.2.1 - - [31/Feb/2025:00:00:00 +0000] "GET / HTTP/1.1" 200 -'
    parsed = ApacheParser().parse(line, NOW)
    assert parsed["timestamp"] == "31/Feb/2025:00:00:00 +0000"
    assert not run_pipeline([line])[0].parse_success


def test_apache_unknown_method_retains_action_and_missing_size():
    record = ApacheParser().parse('192.0.2.1 - - [01/Jan/2025:00:00:00 +0000] "CUSTOM / HTTP/1.1" 200 -', NOW)
    assert (record["activity_id"], record["activity_name"]) == (99, "Other")
    assert record["action"] == "Custom"
    assert record["metadata"]["bytes"] is None


def test_syslog_nearest_year_handles_leap_day_and_invalid_calendar_dates():
    assert SyslogParser._nearest_year("Feb 29 12:00:00", NOW).year == 2024
    with pytest.raises(ValueError, match="Invalid RFC3164 timestamp"):
        SyslogParser._nearest_year("Feb 30 12:00:00", NOW)
    assert SyslogParser._nearest_year("Dec 31 23:59:59", NOW).year == 2024


def test_syslog_nil_timestamp_and_empty_message_remain_explicit():
    record = SyslogParser().parse("<134>1 - host app - - -", NOW)
    assert record["timestamp"] == ""
    assert record["timestamp_missing_ok"] is True
    assert record["message"] == ""


@pytest.mark.parametrize("parser", [Log4jParser(), ApacheParser(), SyslogParser()])
def test_text_detectors_do_not_claim_arbitrary_noise(parser):
    assert parser.detect("malformed arbitrary noise") == 0.0
