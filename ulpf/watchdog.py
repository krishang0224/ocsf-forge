"""Read-only detection of potentially abandoned ingestion runs."""

from datetime import UTC, datetime


def stale_runs(service, timeout_seconds: int) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise ValueError("ULPF_STUCK_RUN_TIMEOUT_SECONDS must be a positive integer")
    _, rows = service.execute(
        "SELECT run_id, started_at FROM iceberg.logging.ingestion_runs "
        "WHERE status = 'RUNNING' AND started_at < date_add('second', ?, current_timestamp) "
        "ORDER BY started_at, run_id LIMIT 101",
        params=[-timeout_seconds], row_limit=101,
    )
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "stale_ingestion_runs" if rows else "ingestion_watchdog_ok",
        "timeout_seconds": timeout_seconds,
        "stale_run_ids": [row[0] for row in rows[:100]],
        "truncated": len(rows) > 100,
        "action": "inspect_and_replay_source" if rows else "none",
    }
