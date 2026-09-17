import io
import json
import subprocess
import sys

import pytest

from ulpf.normalizer import OCSF_CLASS_CATEGORIES
from validation import upstream
from validation.check_ocsf import audit
from validation.fixtures import FIXTURES, cases
from validation.ocsf_contract import check


def test_fixture_exports_match_documented_gaps_and_cover_supported_classes():
    results = audit()
    assert results == json.loads((FIXTURES / "known-gaps.json").read_text())
    assert {result["class_uid"] for result in results} == set(OCSF_CLASS_CATEGORIES)
    assert len(cases()) == 8


@pytest.mark.parametrize("baseline,expected_code", [(False, 1), (True, 0)])
def test_audit_exit_code_distinguishes_failures_from_baseline(baseline, expected_code):
    command = [sys.executable, "-m", "validation.check_ocsf"]
    if baseline:
        command.append("--check-baseline")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == expected_code, result.stderr
    summary = json.loads(result.stdout.splitlines()[-1])
    assert summary["full_schema_conformance"] == "not established"
    baseline_errors = json.loads((FIXTURES / "known-gaps.json").read_text())
    assert summary["failed"] == sum(bool(result["errors"]) for result in baseline_errors)


@pytest.mark.parametrize("value", [None, [], "1.8.0", 1])
def test_invalid_metadata_is_a_failure_not_a_crash(value):
    contract = {"attributes": {"metadata": {"type": "object_t"}}}
    assert "metadata.version must be 1.8.0" in check({"metadata": value}, contract)


def test_partial_checker_rejects_missing_unknown_and_wrong_types():
    contract = {"attributes": {
        "time": {"requirement": "required", "type": "timestamp_t"},
        "severity_id": {"type": "integer_t", "enum": {"1": {}}},
    }}
    errors = check({"severity_id": True, "extra": 1}, contract)
    assert "missing required attribute: time" in errors
    assert "expected integer: severity_id" in errors
    assert "invalid enum: severity_id=True" in errors
    assert "attribute not in selected base class: extra" in errors


@pytest.mark.parametrize("payload", [[], {}, {"errors": [], "error_count": True},
                                      {"errors": [], "error_count": 1}])
def test_upstream_malformed_responses_fail_closed(monkeypatch, payload):
    monkeypatch.setattr(upstream.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode()))
    with pytest.raises(ValueError):
        upstream.validate({})


def test_upstream_request_is_version_pinned(monkeypatch):
    def respond(request, timeout):
        assert request.full_url == "https://schema.ocsf.io/1.8.0/api/v2/validate"
        assert request.get_method() == "POST"
        assert json.loads(request.data) == {"synthetic": True}
        assert timeout == 30
        return io.BytesIO(b'{"errors": [], "error_count": 0}')

    monkeypatch.setattr(upstream.urllib.request, "urlopen", respond)
    assert upstream.validate({"synthetic": True})["error_count"] == 0


def test_upstream_version_mismatch_is_rejected(monkeypatch):
    monkeypatch.setattr(upstream.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b'{"version": "1.9.0"}'))
    with pytest.raises(ValueError, match="Unexpected upstream"):
        upstream.verify_version()
