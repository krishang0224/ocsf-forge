import hashlib

import pytest

from ulpf.parsing.xml_document import MAX_XML_DEPTH
from ulpf.pipeline import run_payload, run_pipeline


@pytest.mark.parametrize("depth", [MAX_XML_DEPTH + 1, 2000])
def test_deep_xml_upload_is_quarantined_with_intact_evidence(depth):
    payload = ("<event>" * depth + "x" + "</event>" * depth).encode()
    event, = run_payload(payload, "deep.xml", max_events=50000)
    assert not event.parse_success
    assert "depth limit" in event.parse_notes
    assert event.original_raw_payload.encode() == payload
    assert event.raw_payload_hash == hashlib.sha256(payload).hexdigest()


def test_depth_budget_also_applies_to_direct_parser_and_preserves_neighbors():
    deep = "<event>" * 2000 + "x" + "</event>" * 2000
    valid = '<event><timestamp>2026-10-13T00:00:00Z</timestamp><message>valid</message></event>'
    events = run_pipeline([valid, deep, valid], forced_format="xml")
    assert [event.parse_success for event in events] == [True, False, True]
    assert events[1].original_raw_payload == deep


def test_xml_at_depth_boundary_is_accepted():
    payload = "<event>" * (MAX_XML_DEPTH - 1) + "<message>valid</message>" + "</event>" * (MAX_XML_DEPTH - 1)
    event, = run_payload(payload.encode(), "boundary.xml")
    assert event.parse_success
    assert event.message == "valid"
