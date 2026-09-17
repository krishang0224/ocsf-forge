import json
import os
import subprocess
from pathlib import Path

import pytest

from validation import check_toolkit, toolkit
from validation.fixtures import cases, export
from validation.prepare_toolkit import fetch_archive


def test_corrupt_cached_archive_is_rejected_before_execution(monkeypatch, tmp_path):
    archive = tmp_path / "schema.tar.gz"
    archive.write_bytes(b"corrupt")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: pytest.fail("unexpected download"))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        fetch_archive({"sha256": "0" * 64}, archive)


def test_bundle_checksum_mismatch_is_not_a_validation_pass(tmp_path):
    executable = tmp_path / "tool"
    executable.write_text("not an executable")
    (tmp_path / "compiled.json").write_text("{}")
    (tmp_path / "manifest.json").write_text(json.dumps({
        "executable": "tool", "lock_sha256": "incorrect", "schema_sha256": "incorrect",
        "executable_sha256": "incorrect",
    }))
    with pytest.raises(ValueError, match="does not match"):
        toolkit.bundle(tmp_path)


@pytest.mark.parametrize("report", [None, [], {}, {"report_version": True, "validation": {}},
                                    {"report_version": 1},
                                    {"report_version": 1, "validation": {"findings": None}},
                                    {"report_version": 1, "validation": {"findings": [{}]}},
                                    {"report_version": 1, "validation": {}, "issues": ["incomplete"]}])
def test_malformed_or_incomplete_toolkit_reports_fail_closed(report):
    with pytest.raises(ValueError):
        toolkit.signatures(report)


def test_toolkit_does_not_enrich_or_suppress_validation_checks(monkeypatch):
    def run(command, **kwargs):
        assert command[-3:] == ["--validate", "--report-output", "-"]
        assert "--enrich" not in command
        assert "--validation-level" not in command
        assert json.loads(Path(command[command.index("--event") + 1]).read_text()) == {"test": 1}
        assert kwargs["timeout"] == 30
        assert kwargs["check"] is True
        return subprocess.CompletedProcess(command, 0, '{"report_version":1,"validation":{}}', "")

    monkeypatch.setattr(toolkit.subprocess, "run", run)
    assert toolkit.validate({"test": 1}, "tool", "schema") == []


def test_toolkit_initialization_warnings_are_not_treated_as_a_pass(monkeypatch):
    monkeypatch.setattr(toolkit.subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess([], 0, '{"report_version":1,"validation":{}}', "schema issue"))
    with pytest.raises(ValueError, match="initialization"):
        toolkit.validate({}, "tool", "schema")


def test_swapping_which_fixture_fails_cannot_preserve_a_green_gate(monkeypatch):
    monkeypatch.setattr(check_toolkit, "bundle", lambda _: ("tool", "schema"))
    missing_endpoint = ["error", "validation_attribute_required_missing", "src_endpoint"]
    def validate(record, *_):
        return [missing_endpoint] if record["class_uid"] == 3002 else []
    monkeypatch.setattr(check_toolkit, "validate", validate)
    results = {result["fixture"]: result for result in check_toolkit.audit("unused")}
    assert not results["json-authentication"]["matched"]
    assert not results["csv-api"]["matched"]


def test_negative_fixture_failing_for_wrong_reason_is_a_regression(monkeypatch):
    monkeypatch.setattr(check_toolkit, "bundle", lambda _: ("tool", "schema"))
    monkeypatch.setattr(check_toolkit, "validate", lambda *_:
                        [["error", "validation_attribute_required_missing", "time"]])
    result = next(result for result in check_toolkit.audit("unused") if result["fixture"] == "csv-api")
    assert not result["matched"]


def test_missing_fixture_expectations_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(check_toolkit, "bundle", lambda _: ("tool", "schema"))
    expectations = tmp_path / "empty.json"
    expectations.write_text("{}")
    monkeypatch.setattr(check_toolkit, "EXPECTED", expectations)
    with pytest.raises(ValueError, match="Fixture set"):
        check_toolkit.audit("unused")


def test_toolkit_execution_failure_has_infrastructure_exit_code(monkeypatch):
    monkeypatch.setattr("sys.argv", ["check_toolkit"])
    def unavailable(_):
        raise subprocess.TimeoutExpired("toolkit", 30)
    monkeypatch.setattr(check_toolkit, "audit", unavailable)
    assert check_toolkit.main() == 2


@pytest.fixture
def real_bundle():
    directory = os.getenv("ULPF_OCSF_TOOLKIT_DIRECTORY")
    if not directory:
        pytest.skip("requires prepared official toolkit; mandatory in the OCSF CI job")
    return directory


def test_official_toolkit_matches_every_original_fixture(real_bundle):
    results = check_toolkit.audit(real_bundle)
    assert len(results) == 8
    assert all(result["matched"] for result in results)


@pytest.mark.parametrize("case_name,field,value,path,expected_level", [
    ("json-authentication", "user", {"name": 123}, "user.name", "error"),
    ("apache-http", "http_response", {"code": "403"}, "http_response.code", "error"),
    ("xml-api", "src_endpoint", {"ip": "not-an-ip"}, "src_endpoint.ip", "warning"),
])
def test_official_toolkit_rejects_nested_regressions(real_bundle, case_name, field, value, path, expected_level):
    executable, schema = toolkit.bundle(real_bundle)
    record = export(next(case for case in cases() if case["name"] == case_name))
    record[field] = value
    findings = toolkit.validate(record, executable, schema)
    assert any(level == expected_level and attribute == path for level, _, attribute in findings), findings
    assert findings != json.loads(check_toolkit.EXPECTED.read_text())[case_name]


def test_official_toolkit_detects_additional_error_in_known_negative(real_bundle):
    executable, schema = toolkit.bundle(real_bundle)
    record = export(next(case for case in cases() if case["name"] == "csv-api"))
    record["actor"]["user"]["name"] = 123
    findings = toolkit.validate(record, executable, schema)
    assert ["error", "validation_attribute_required_missing", "src_endpoint"] in findings
    assert any(path == "actor.user.name" for _, _, path in findings)
    assert len(findings) > 1
