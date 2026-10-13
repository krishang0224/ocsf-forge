"""Synthetic Kafka ingestion and outage audit for an explicitly disposable stack."""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from ulpf.config import settings
from ulpf.sample_data import SAMPLE_LOGS
from ulpf.services.trino import TrinoService


def wait_offset(observer, topic, expected, worker, timeout=180):
    from kafka import TopicPartition

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if worker.poll() is not None:
            raise RuntimeError(f"Worker stopped with exit code {worker.returncode}")
        if (observer.committed(TopicPartition(topic, 0)) or 0) >= expected:
            return
        time.sleep(1)
    raise TimeoutError(f"Kafka committed offset did not reach {expected}")


def payload(index):
    if index % 10:
        return SAMPLE_LOGS[index % len(SAMPLE_LOGS)].encode()
    return (b"malformed event", None, b"\xff", ("<event>" * 2000 + "x" + "</event>" * 2000).encode())[(index // 10) % 4]


def cleanup_worker(worker, producer, observer, runtime, container, paused):
    errors = []
    if paused:
        try:
            subprocess.run([runtime, "unpause", container], check=True, capture_output=True)
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append({"action": "unpause", "error": str(exc)})
    try:
        worker.terminate()
        try:
            worker.wait(timeout=30)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
    finally:
        for name, close in (("producer", lambda: producer.close(timeout=10)), ("observer", observer.close)):
            try:
                close()
            except Exception as exc:
                errors.append({"action": f"close-{name}", "error": str(exc)})
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-test-stack", action="store_true", required=True)
    parser.add_argument("--trino-container", required=True)
    parser.add_argument("--runtime", choices=("docker", "podman"), default="docker")
    parser.add_argument("--brokers", default="localhost:9092")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--messages", type=int, default=5000)
    args = parser.parse_args()
    if args.messages < 2000 or args.messages % 1000:
        parser.error("messages must be at least 2,000 and a multiple of 1,000")
    from kafka import KafkaConsumer, KafkaProducer, TopicPartition
    from kafka.admin import KafkaAdminClient, NewTopic

    topic = f"stress-{uuid.uuid4().hex}"
    dead = topic + "-dead"
    group = topic + "-consumer"
    first = args.messages - 1000
    started = time.perf_counter()
    admin = KafkaAdminClient(bootstrap_servers=args.brokers)
    admin.create_topics([NewTopic(topic, 1, 1), NewTopic(dead, 1, 1)])
    admin.close()
    producer = KafkaProducer(bootstrap_servers=args.brokers, acks="all", enable_idempotence=True)
    observer = KafkaConsumer(bootstrap_servers=args.brokers, group_id=group, enable_auto_commit=False)
    environment = {**os.environ, "TRINO_HOST": args.host, "TRINO_USER": "ulpf_writer", "TRINO_REQUEST_TIMEOUT": "3",
                   "KAFKA_BOOTSTRAP_SERVERS": args.brokers, "KAFKA_TOPIC": topic,
                   "KAFKA_DEAD_LETTER_TOPIC": dead, "KAFKA_CONSUMER_GROUP": group, "KAFKA_BATCH_SIZE": "500"}
    paused = False
    with TemporaryDirectory(prefix="forge-stream-stress-") as directory:
        with (Path(directory) / "worker.log").open("w") as log:
            worker = subprocess.Popen([sys.executable, "-m", "ulpf.streaming.worker"], env=environment, stdout=log, stderr=log)
            try:
                for index in range(first):
                    producer.send(topic, key=str(index).encode(), value=payload(index)).get(timeout=30)
                producer.flush()
                wait_offset(observer, topic, first, worker)
                subprocess.run([args.runtime, "pause", args.trino_container], check=True, capture_output=True)
                paused = True
                for index in range(first, args.messages):
                    producer.send(topic, key=str(index).encode(), value=payload(index)).get(timeout=30)
                producer.flush()
                time.sleep(5)
                held = observer.committed(TopicPartition(topic, 0))
                assert held == first, held
                print(json.dumps({"case": "kafka-offset-held-during-trino-outage", "ok": True, "offset": held}), flush=True)
                subprocess.run([args.runtime, "unpause", args.trino_container], check=True, capture_output=True)
                paused = False
                wait_offset(observer, topic, args.messages, worker)
                service = TrinoService(replace(settings, trino_host=args.host, trino_user="ulpf_writer", trino_request_timeout=30))
                source = f"kafka:{topic}:0"
                expected_bad = args.messages // 10
                counts = {}
                for table, expected in (("raw_events", args.messages), ("application_logs", args.messages - expected_bad),
                                        ("quarantine_events", expected_bad)):
                    _, rows = service.execute(f"SELECT count(*), count(DISTINCT event_id) FROM iceberg.logging.{table} WHERE source_id=?", [source])
                    assert rows == [[expected, expected]], (table, rows)
                    counts[table] = expected
                letters = KafkaConsumer(dead, bootstrap_servers=args.brokers, enable_auto_commit=False, auto_offset_reset="earliest")
                try:
                    ids = []
                    deadline = time.monotonic() + 30
                    while len(ids) < expected_bad and time.monotonic() < deadline:
                        for records in letters.poll(timeout_ms=1000).values():
                            ids.extend(json.loads(record.value)["event_id"] for record in records)
                    assert len(ids) == len(set(ids)) == expected_bad, (len(ids), len(set(ids)))
                finally:
                    letters.close()
                print(json.dumps({"case": "kafka-outage-recovery", "ok": True, "seconds": round(time.perf_counter() - started, 3),
                                  "topic": topic, **counts, "unique_dead_letters": len(ids), "committed_offset": args.messages}), flush=True)
            finally:
                cleanup_errors = cleanup_worker(worker, producer, observer, args.runtime, args.trino_container, paused)
                if cleanup_errors:
                    print(json.dumps({"case": "streaming-test-cleanup", "ok": False, "errors": cleanup_errors}), flush=True)
    return 1 if cleanup_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
