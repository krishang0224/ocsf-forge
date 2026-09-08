from unittest.mock import Mock

import pytest

from ulpf.ui.detections import _load_evidence


def test_evidence_lookup_binds_ids_and_limits_results():
    _load_evidence.clear()
    trino = Mock()
    trino.execute.return_value = (["event_id"], [["event-a"]])
    malicious = "'; DROP TABLE x; --"
    assert _load_evidence(trino, ("event-a", malicious)) == [{"event_id": "event-a"}]
    statement, params = trino.execute.call_args.args
    assert malicious not in statement
    assert params == ["event-a", malicious]
    assert trino.execute.call_args.kwargs["row_limit"] == 200


@pytest.mark.parametrize("ids", [(), ("id",) * 201, (123,)])
def test_invalid_evidence_requests_do_not_query(ids):
    trino = Mock()
    with pytest.raises(ValueError):
        _load_evidence(trino, ids)
    trino.execute.assert_not_called()
