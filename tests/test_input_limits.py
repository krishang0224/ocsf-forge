from dataclasses import replace
from unittest.mock import Mock

import pytest

from ulpf.config import settings
from ulpf.normalizer import OCSFNormalizer
from ulpf.parsing.limits import InputLimitError
from ulpf.pipeline import run_payload, run_pipeline
from ulpf.sample_data import SAMPLE_LOGS


@pytest.mark.parametrize(("payload", "filename"), [
    (b'{}\n{}\n{}\n{}', "events.jsonl"),
    (b'[{},{},{},{}]', "events.json"),
    (b'message\na\nb\nc\nd\n', "events.csv"),
    (b'<events><event/><event/><event/><event/></events>', "events.xml"),
])
def test_limit_rejects_complete_document_before_normalizing_any_records(payload, filename, monkeypatch):
    normalize = Mock(side_effect=AssertionError("normalization must not start"))
    monkeypatch.setattr(OCSFNormalizer, "normalize", normalize)
    with pytest.raises(InputLimitError, match="3-event"):
        run_payload(payload, filename, max_events=3)
    normalize.assert_not_called()


def test_limit_counts_csv_records_not_embedded_newlines():
    events = run_payload(b'message\n"first\nsecond"\n', "events.csv", max_events=1)
    assert len(events) == 1 and events[0].message == "first\nsecond"


def test_limit_counts_log4j_events_not_stack_trace_lines():
    events = run_pipeline([SAMPLE_LOGS[-1], "    at example.method()"], max_events=1)
    assert len(events) == 1


def test_limit_boundary_empty_documents_and_unbounded_api():
    assert len(run_payload(b'{}\n{}', max_events=2)) == 2
    assert run_payload(b"", max_events=1) == []
    assert len(run_payload(b'{}\n{}')) == 2
    with pytest.raises(ValueError, match="positive"):
        run_payload(b"", max_events=0)
    with pytest.raises(ValueError, match="positive"):
        replace(settings, max_upload_events=0)


def test_ui_rejection_disables_ingestion_and_shows_limit(monkeypatch):
    from ulpf.ui import ingestion

    monkeypatch.setattr(ingestion, "settings", replace(settings, max_upload_events=1))
    ui = Mock()
    monkeypatch.setattr(ingestion, "st", ui)
    assert ingestion._interactive_payload(b'{}\n{}', "events.jsonl") == []
    assert "1-event" in ui.error.call_args.args[0]
