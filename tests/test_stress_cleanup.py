import subprocess
from unittest.mock import Mock

from benchmarks.lakehouse import cleanup_sources
from benchmarks.streaming import cleanup_worker


def test_stress_cleanup_continues_after_failure_and_does_not_raise_over_original_error():
    backend = Mock()
    backend.execute.side_effect = [RuntimeError("engine unavailable"), ([], []), ([], []), ([], [])]
    errors = cleanup_sources(backend, ["owned-test-source"])
    assert len(errors) == 1
    assert errors[0]["table"] == "application_logs"
    assert errors[0]["source_id"] == "owned-test-source"
    assert backend.execute.call_count == 4
    assert all(call.args[1] == ["owned-test-source"] for call in backend.execute.call_args_list)


def test_streaming_worker_stops_even_if_container_resume_fails(monkeypatch):
    worker, producer, observer = Mock(), Mock(), Mock()
    def unavailable(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])
    monkeypatch.setattr("benchmarks.streaming.subprocess.run", unavailable)
    errors = cleanup_worker(worker, producer, observer, "podman", "owned-test-container", True)
    assert errors[0]["action"] == "unpause"
    worker.terminate.assert_called_once()
    worker.wait.assert_called_once_with(timeout=30)
    producer.close.assert_called_once()
    observer.close.assert_called_once()
