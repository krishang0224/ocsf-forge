"""Opt-in Trino stress checks against an explicitly selected disposable stack."""

import argparse
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter

from ulpf import sql
from ulpf.config import settings
from ulpf.pipeline import run_pipeline
from ulpf.sample_data import SAMPLE_LOGS
from ulpf.services.trino import TrinoService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-test-stack", action="store_true", required=True)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--rows", nargs="+", type=int, default=[2500, 10000])
    args = parser.parse_args()
    if min(args.rows) <= 0:
        parser.error("rows must be positive")
    config = replace(settings, trino_host=args.host, trino_user="ulpf_writer", trino_request_timeout=30)
    backend = TrinoService(config)
    backend.ensure_lakehouse()
    prefix = f"stress-{uuid.uuid4().hex}"
    sources = []

    def source(label):
        identity = f"{prefix}-{label}"
        sources.append(identity)
        return identity

    def check(name, operation):
        started = perf_counter()
        details = operation()
        print(json.dumps({"case": name, "ok": True, "seconds": round(perf_counter() - started, 3), "details": details}), flush=True)

    try:
        for count in args.rows:
            def scale(count=count):
                events = run_pipeline([SAMPLE_LOGS[i % len(SAMPLE_LOGS)] for i in range(count)], source_id=source(str(count)))
                result = backend.ingest_events(events)
                assert result.committed == count, result
                replay = backend.ingest_events(events)
                assert replay.committed == 0 and replay.duplicates == count, replay
                return {"committed": count, "duplicates": replay.duplicates}
            check(f"ingest-and-replay-{count}", scale)

        def simultaneous():
            identity = source("concurrent")
            events = run_pipeline(SAMPLE_LOGS * 125, source_id=identity)
            with ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(lambda _: TrinoService(config).ingest_events(events), range(3)))
            assert sum(r.committed for r in results) == 1000, results
            assert sum(r.duplicates for r in results) == 2000, results
            for table in ("raw_events", "application_logs"):
                _, rows = backend.execute(f"SELECT count(*), count(DISTINCT event_id) FROM iceberg.logging.{table} WHERE source_id=?", [identity])
                assert rows == [[1000, 1000]], rows
            return {"writers": 3, "unique": 1000}
        check("concurrent-writers", simultaneous)

        def timestamps():
            events = run_pipeline(['{"timestamp":"2026-09-10T12:34:56.123456+05:30","message":"timestamp"}', '{"message":"\\ud800"}'], source_id=source("timestamp"))
            result = backend.ingest_events(events)
            assert (result.committed, result.quarantined) == (1, 1), result
            _, rows = backend.execute("SELECT event_timestamp, timezone_offset FROM iceberg.logging.application_logs WHERE event_id=?", [events[0].event_id])
            assert rows == [[datetime(2026, 9, 10, 7, 4, 56, 123456, tzinfo=UTC), 330]], rows
            return {"microseconds": 123456, "offset_minutes": 330, "quarantined": 1}
        check("timestamp-and-malformed-neighbor", timestamps)

        def recovery():
            class Interrupted(TrinoService):
                def _merge_batches(self, connection, table, *args):
                    if table == self.config.qualified_table:
                        raise RuntimeError("injected interruption after raw commit")
                    return super()._merge_batches(connection, table, *args)

            identity = source("recovery")
            events = run_pipeline(SAMPLE_LOGS, source_id=identity)
            try:
                Interrupted(config).ingest_events(events)
            except RuntimeError as exc:
                assert "injected interruption" in str(exc)
            else:
                raise AssertionError("failure injection did not run")
            result = backend.ingest_events(events)
            assert result.committed == 8, result
            for table in ("raw_events", "application_logs"):
                assert backend.execute(f"SELECT count(*) FROM iceberg.logging.{table} WHERE source_id=?", [identity])[1] == [[8]]
            return {"recovered": 8}
        check("partial-commit-recovery", recovery)

        def dashboard():
            reader = TrinoService(replace(config, trino_user="ulpf_dashboard"))
            queries = {name: getattr(sql, name) for name in (
                "OVERVIEW_QUERY", "RECENT_QUERY", "SEVERITY_QUERY", "SERVICE_QUERY", "QUALITY_QUERY", "RUNS_QUERY", "WAREHOUSE_QUERY",
            )}
            assert set(reader.query_many(queries)) == set(queries)
            return {"queries": len(queries)}
        check("dashboard-query-bundle", dashboard)
    finally:
        for identity in sources:
            for table in ("application_logs", "raw_events", "quarantine_events", "ingestion_runs"):
                backend.execute(f"DELETE FROM iceberg.logging.{table} WHERE source_id=?", [identity])


if __name__ == "__main__":
    main()
