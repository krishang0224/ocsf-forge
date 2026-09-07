"""Iceberg compaction and retention scheduler."""

import json
import os
import signal
import threading
from datetime import UTC, datetime

from ulpf.services.trino import TrinoService

MAINTAINABLE_TABLES = ("raw_events", "application_logs", "quarantine_events", "ingestion_runs", "detections")


def run_once(service: TrinoService | None = None) -> dict:
    trino = service or TrinoService()
    minimum_files = int(os.getenv("ULPF_COMPACTION_MIN_FILES", "50"))
    target_mb = int(os.getenv("ULPF_COMPACTION_TARGET_MB", "128"))
    snapshot_days = max(1, int(os.getenv("ULPF_SNAPSHOT_RETENTION_DAYS", "7")))
    orphan_days = max(3, int(os.getenv("ULPF_ORPHAN_RETENTION_DAYS", "7")))
    configured = tuple(
        name.strip()
        for name in os.getenv("ULPF_MAINTENANCE_TABLES", ",".join(MAINTAINABLE_TABLES)).split(",")
        if name.strip()
    )
    unknown = set(configured) - set(MAINTAINABLE_TABLES)
    if unknown:
        raise ValueError(f"Unsupported maintenance tables: {', '.join(sorted(unknown))}")
    table_metrics = {}
    for table in configured:
        _, rows = trino.execute(
            f'SELECT count(*), coalesce(avg(file_size_in_bytes), 0) FROM iceberg.logging."{table}$files"'
        )
        file_count, average_bytes = rows[0]
        compacted = file_count >= minimum_files and average_bytes < target_mb * 1024 * 1024 * 0.5
        if compacted:
            trino.execute(
                f"ALTER TABLE iceberg.logging.{table} EXECUTE optimize(file_size_threshold => '{target_mb}MB')"
            )
        trino.execute(
            f"ALTER TABLE iceberg.logging.{table} EXECUTE expire_snapshots(retention_threshold => '{snapshot_days}d')"
        )
        trino.execute(
            f"ALTER TABLE iceberg.logging.{table} EXECUTE remove_orphan_files(retention_threshold => '{orphan_days}d')"
        )
        table_metrics[table] = {
            "data_files": file_count,
            "average_file_bytes": int(average_bytes),
            "compacted": compacted,
        }
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "data_files": sum(metrics["data_files"] for metrics in table_metrics.values()),
        "compacted": any(metrics["compacted"] for metrics in table_metrics.values()),
        "tables": table_metrics,
        "snapshot_retention_days": snapshot_days,
        "orphan_retention_days": orphan_days,
    }


def main() -> None:
    interval = max(3600, int(os.getenv("ULPF_MAINTENANCE_INTERVAL_SECONDS", "86400")))
    stopped = threading.Event()

    def stop(*_args) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopped.is_set():
        delay = interval
        try:
            print(json.dumps(run_once(), separators=(",", ":")), flush=True)
        except Exception as exc:
            print(json.dumps({"timestamp": datetime.now(UTC).isoformat(), "error": str(exc)}), flush=True)
            delay = min(60, interval)
        stopped.wait(delay)


if __name__ == "__main__":
    main()
