import json
from dataclasses import replace

import pytest

from ulpf.pipeline import run_pipeline


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
