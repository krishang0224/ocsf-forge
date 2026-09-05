import threading

from ulpf.models import IngestionResult
from ulpf.streaming.retry import ingest_with_retry, initialize_with_retry


class FlakyService:
    def __init__(self, failures):
        self.failures = failures
        self.attempts = 0

    def ingest_events(self, events):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ConnectionError("Trino unavailable")
        return IngestionResult("run", len(events), len(events), 0, 0, "COMPLETED")

    def ensure_lakehouse(self):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ConnectionError("Trino unavailable")


def test_transient_storage_failure_retries_the_same_batch():
    service = FlakyService(failures=2)
    result = ingest_with_retry(service, [object()], threading.Event(), initial_delay=0)
    assert result.status == "COMPLETED"
    assert service.attempts == 3


def test_shutdown_interrupts_retry_backoff():
    stopped = threading.Event()
    stopped.set()
    service = FlakyService(failures=1)
    assert ingest_with_retry(service, [object()], stopped, initial_delay=0) is None
    assert service.attempts == 0


def test_transient_initialization_failure_is_retried():
    service = FlakyService(failures=2)
    assert initialize_with_retry(service, threading.Event(), initial_delay=0)
    assert service.attempts == 3


def test_shutdown_interrupts_initialization_retry():
    stopped = threading.Event()
    stopped.set()
    service = FlakyService(failures=1)
    assert not initialize_with_retry(service, stopped, initial_delay=0)
    assert service.attempts == 0
