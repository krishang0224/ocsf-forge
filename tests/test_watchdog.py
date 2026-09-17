from unittest.mock import Mock

import pytest

from ulpf.watchdog import stale_runs


def test_stale_watchdog_is_parameterized_read_only_and_bounded():
    service = Mock()
    service.execute.return_value = ([], [[f"run-{i}", None] for i in range(101)])
    result = stale_runs(service, 3600)
    statement = service.execute.call_args.args[0]
    assert statement.startswith("SELECT")
    assert "status = 'RUNNING'" in statement
    assert "started_at < date_add('second', ?, current_timestamp)" in statement
    assert "LIMIT 101" in statement
    assert service.execute.call_args.kwargs == {"params": [-3600], "row_limit": 101}
    assert result["event"] == "stale_ingestion_runs"
    assert result["truncated"] is True
    assert len(result["stale_run_ids"]) == 100


def test_watchdog_empty_and_unavailable_are_distinct():
    service = Mock()
    service.execute.return_value = ([], [])
    assert stale_runs(service, 10)["event"] == "ingestion_watchdog_ok"
    service.execute.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError):
        stale_runs(service, 10)


@pytest.mark.parametrize("timeout", [0, -1, True, "10"])
def test_watchdog_rejects_invalid_timeout(timeout):
    service = Mock()
    with pytest.raises(ValueError):
        stale_runs(service, timeout)
    service.execute.assert_not_called()


def test_scheduler_checks_watchdog_without_repeating_compaction(monkeypatch):
    from ulpf import maintenance

    stopped = Mock()
    stopped.is_set.side_effect = [False, False, True]
    monkeypatch.setattr(maintenance.threading, "Event", lambda: stopped)
    monkeypatch.setattr(maintenance.signal, "signal", Mock())
    monkeypatch.setattr(maintenance.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(maintenance, "TrinoService", Mock())
    maintain = Mock(return_value={})
    watchdog = Mock(return_value={})
    monkeypatch.setattr(maintenance, "run_once", maintain)
    monkeypatch.setattr(maintenance, "stale_runs", watchdog)
    monkeypatch.setenv("ULPF_WATCHDOG_INTERVAL_SECONDS", "300")
    monkeypatch.setenv("ULPF_MAINTENANCE_INTERVAL_SECONDS", "86400")
    monkeypatch.setenv("ULPF_STUCK_RUN_TIMEOUT_SECONDS", "3600")
    maintenance.main()
    assert watchdog.call_count == 2
    assert maintain.call_count == 1
    assert stopped.wait.call_count == 2
    stopped.wait.assert_called_with(300)
