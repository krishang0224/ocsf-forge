"""Retry transient storage failures without advancing Kafka."""

import logging
import threading

from ulpf.models import IngestionResult, NormalizedEvent
from ulpf.services.trino import TrinoService

LOGGER = logging.getLogger(__name__)


def initialize_with_retry(
    service: TrinoService,
    stopped: threading.Event,
    *,
    initial_delay: float = 1.0,
    maximum_delay: float = 30.0,
) -> bool:
    delay = initial_delay
    while not stopped.is_set():
        try:
            service.ensure_lakehouse()
            return True
        except Exception:
            LOGGER.exception("Storage initialization failed; retrying in %.1f seconds", delay)
            if stopped.wait(delay):
                return False
            delay = min(delay * 2, maximum_delay)
    return False


def ingest_with_retry(
    service: TrinoService,
    events: list[NormalizedEvent],
    stopped: threading.Event,
    *,
    initial_delay: float = 1.0,
    maximum_delay: float = 30.0,
) -> IngestionResult | None:
    delay = initial_delay
    while not stopped.is_set():
        try:
            return service.ingest_events(events)
        except Exception:
            LOGGER.exception("Storage write failed; retrying the Kafka batch in %.1f seconds", delay)
            if stopped.wait(delay):
                return None
            delay = min(delay * 2, maximum_delay)
    return None
