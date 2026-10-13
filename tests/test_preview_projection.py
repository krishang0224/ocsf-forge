from unittest.mock import patch

import pytest

from ulpf.pipeline import events_to_frame, run_pipeline


def test_preview_projection_preserves_displayed_values_without_copying_hidden_metadata():
    events = run_pipeline(['{"message":"preview","extra":[1,2,3]}', 'malformed'])
    columns = ["timestamp", "message", "severity", "parse_success", "raw_payload_hash"]
    expected = events_to_frame(events)[columns]
    with patch("ulpf.models.NormalizedEvent.to_dict", side_effect=AssertionError("copied hidden metadata")):
        projected = events_to_frame(events, columns=columns)
    assert projected.equals(expected)


def test_projection_keeps_empty_schema_and_requires_explicit_raw_access():
    assert events_to_frame([], columns=["message"]).columns.tolist() == ["message"]
    with pytest.raises(ValueError, match="include_raw"):
        events_to_frame([], columns=["original_raw_payload"])
    with pytest.raises(ValueError, match="Unknown event columns"):
        events_to_frame([], columns=["not_a_field"])
