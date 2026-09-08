"""Kafka record boundaries and acknowledged dead-letter delivery."""

import base64
import json
from datetime import UTC, datetime


def parse_record(processor, record):
    observed = datetime.fromtimestamp(record.timestamp / 1000, UTC) if record.timestamp >= 0 else datetime.now(UTC)
    source = {"source_id": f"kafka:{record.topic}:{record.partition}", "source_name": record.topic, "observed_at": observed}
    reason = ""
    metadata = {}
    if record.value is None:
        payload, reason = "", "Kafka tombstone is not a log event"
        metadata["kafka_tombstone"] = True
    else:
        try:
            payload = record.value.decode("utf-8")
        except UnicodeDecodeError:
            payload = record.value.decode("utf-8", errors="backslashreplace")
            reason = "Kafka event is not valid UTF-8"
            metadata["raw_bytes_base64"] = base64.b64encode(record.value).decode("ascii")
        if not payload.strip():
            reason = "Empty Kafka log event"
    if reason:
        return processor.normalizer.normalize(
            payload, "unknown", {"_parsed": False, "parse_notes": reason, "metadata": metadata},
            source_offset=record.offset, **source,
        )
    return processor.run([payload], source_offset_start=record.offset, **source)[0]


def publish_dead_letters(producer, topic, events):
    pending = [producer.send(
        topic, key=event.event_id.encode(),
        value=json.dumps({
            "event_id": event.event_id, "source_id": event.source_id, "source_offset": event.source_offset,
            "error": event.parse_notes, "raw_payload": event.original_raw_payload,
            "metadata": event.metadata,
        }, separators=(",", ":")).encode(),
    ) for event in events if not event.parse_success]
    if pending:
        producer.flush()
        for future in pending:
            future.get(timeout=30)
