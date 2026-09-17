import json
from dataclasses import replace

import pytest

from ulpf.pipeline import run_pipeline
from validation.fixtures import FIXTURES, cases, export
from validation.ocsf_contract import check


@pytest.mark.parametrize("line", [
    "CEF:0|Vendor|Product|1|42|Finding|7|src=192.0.2.10",
    "LEEF:1.0|Vendor|Product|1|42|src=192.0.2.10",
])
def test_findings_retain_endpoints_and_user_without_forbidden_root_attributes(line):
    event = replace(run_pipeline([line])[0], user="alice", dst_endpoint_ip="198.51.100.2",
                    metadata={"normalized_context": "vendor value"})
    record = event.to_ocsf_dict()
    assert not {"src_endpoint", "dst_endpoint", "actor"} & record.keys()
    context = record["unmapped"]["normalized_context"]
    assert context["src_endpoint"]["ip"] == "192.0.2.10"
    assert context["dst_endpoint"]["ip"] == "198.51.100.2"
    assert context["actor"]["user"]["name"] == "alice"
    assert record["unmapped"]["source_fields"]["normalized_context"] == "vendor value"
    assert event.metadata == {"normalized_context": "vendor value"}


def test_authentication_exports_target_user_and_explicit_service():
    event = run_pipeline([json.dumps({"action": "login_failure", "user": "alice", "service": "ssh"})])[0]
    record = event.to_ocsf_dict()
    assert record["user"] == {"name": "alice"}
    assert record["service"] == {"name": "ssh"}
    assert "actor" not in record


def test_authentication_does_not_invent_missing_service_or_user():
    record = run_pipeline(['{"action":"login_failure"}'])[0].to_ocsf_dict()
    assert "service" not in record
    assert "user" not in record


@pytest.mark.parametrize("size", ["123", "-"])
def test_http_exports_response_and_preserves_request_and_authenticated_user(size):
    line = f'192.0.2.1 - alice [01/Sep/2026:00:00:00 +0000] "POST /submit HTTP/1.1" 403 {size}'
    record = run_pipeline([line])[0].to_ocsf_dict()
    assert record["http_response"]["code"] == 403
    assert "actor" not in record
    assert record["unmapped"]["normalized_context"]["actor"]["user"]["name"] == "alice"
    assert record["unmapped"]["path"] == "/submit"
    assert record["unmapped"]["protocol"] == "HTTP/1.1"
    if size == "-":
        assert "body_length" not in record["http_response"]
    else:
        assert record["http_response"]["body_length"] == 123


def test_incomplete_api_fixture_remains_a_visible_failure_without_invented_endpoint():
    case = next(case for case in cases() if case["name"] == "csv-api")
    record = export(case)
    assert "src_endpoint" not in record
    contract = json.loads((FIXTURES / "contracts/api_activity.json").read_text())
    assert "missing required attribute: src_endpoint" in check(record, contract)
