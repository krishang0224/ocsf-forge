"""Kafka micro-batch worker with offset-based idempotency and backpressure."""

import json
import os
import signal
from datetime import UTC, datetime

from kafka import KafkaConsumer, KafkaProducer

from ulpf.pipeline import EventProcessor
from ulpf.services.trino import TrinoService


def main() -> None:
    brokers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092").split(",")
    topic = os.getenv("KAFKA_TOPIC", "raw-app-logs")
    dead_letter_topic = os.getenv("KAFKA_DEAD_LETTER_TOPIC", "ulpf-dead-letter")
    batch_size = int(os.getenv("KAFKA_BATCH_SIZE", "500"))
    running = True

    def stop(*_args) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=brokers,
        group_id=os.getenv("KAFKA_CONSUMER_GROUP", "ulpf-normalizer-v1"),
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        max_poll_records=batch_size,
        max_poll_interval_ms=int(os.getenv("KAFKA_MAX_POLL_INTERVAL_MS", "900000")),
    )
    producer = KafkaProducer(
        bootstrap_servers=brokers,
        acks="all",
        enable_idempotence=True,
    )
    trino = TrinoService()
    processor = EventProcessor()
    trino.ensure_lakehouse()
    try:
        while running:
            polled = consumer.poll(timeout_ms=1000, max_records=batch_size)
            records = [record for partition in polled.values() for record in partition]
            if not records:
                continue
            events = []
            for record in records:
                observed = datetime.fromtimestamp(record.timestamp / 1000, UTC)
                source_id = f"kafka:{record.topic}:{record.partition}"
                event = processor.run(
                    [record.value.decode("utf-8", errors="replace")],
                    source_id=source_id,
                    source_name=record.topic,
                    source_offset_start=record.offset,
                    observed_at=observed,
                )[0]
                events.append(event)
            result = trino.ingest_events(events)
            for event in events:
                if not event.parse_success:
                    producer.send(
                        dead_letter_topic,
                        key=event.event_id.encode(),
                        value=json.dumps(
                            {
                                "event_id": event.event_id,
                                "source_id": event.source_id,
                                "source_offset": event.source_offset,
                                "error": event.parse_notes,
                                "raw_payload": event.original_raw_payload,
                            },
                            separators=(",", ":"),
                        ).encode(),
                    )
            producer.flush()
            if result.status in {"COMPLETED", "COMPLETED_WITH_QUARANTINE"}:
                consumer.commit()
    finally:
        producer.close()
        consumer.close()


if __name__ == "__main__":
    main()
