"""Kafka micro-batch worker with offset-based idempotency and backpressure."""

import os
import signal
import threading

from kafka import KafkaConsumer, KafkaProducer

from ulpf.pipeline import EventProcessor
from ulpf.services.trino import TrinoService
from ulpf.streaming.records import parse_record, publish_dead_letters
from ulpf.streaming.retry import ingest_with_retry, initialize_with_retry


def main() -> None:
    brokers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092").split(",")
    topic = os.getenv("KAFKA_TOPIC", "raw-app-logs")
    dead_letter_topic = os.getenv("KAFKA_DEAD_LETTER_TOPIC", "ulpf-dead-letter")
    batch_size = int(os.getenv("KAFKA_BATCH_SIZE", "500"))
    stopped = threading.Event()

    def stop(*_args) -> None:
        stopped.set()

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
    try:
        if not initialize_with_retry(trino, stopped):
            return
        while not stopped.is_set():
            polled = consumer.poll(timeout_ms=1000, max_records=batch_size)
            records = [record for partition in polled.values() for record in partition]
            if not records:
                continue
            events = [parse_record(processor, record) for record in records]
            result = ingest_with_retry(trino, events, stopped)
            if result is None:
                break
            publish_dead_letters(producer, dead_letter_topic, events)
            if result.status in {"COMPLETED", "COMPLETED_WITH_QUARANTINE"}:
                consumer.commit()
    finally:
        producer.close()
        consumer.close()


if __name__ == "__main__":
    main()
