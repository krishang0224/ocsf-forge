"""Opt-in load and recovery checks: python -m benchmarks.homelab.

Uses a temporary database, never the configured homelab directory.
"""

import argparse
import json
import resource
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from tempfile import TemporaryDirectory
from time import perf_counter

from ulpf import sql
from ulpf.config import settings
from ulpf.pipeline import run_pipeline
from ulpf.sample_data import SAMPLE_LOGS
from ulpf.services.duckdb_backend import DuckDBBackend


def measure(name, operation):
    started = perf_counter()
    try:
        details = operation()
        result = {"case": name, "ok": True, "details": details}
    except Exception as exc:
        result = {"case": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result.update(seconds=round(perf_counter() - started, 3), peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    print(json.dumps(result), flush=True)
    return result["ok"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", nargs="+", type=int, default=[2500, 10000, 25000, 50000, 100000])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--chunked-rows", type=int, default=0, help="additional events in separate 10,000-event commits")
    args = parser.parse_args()
    if min(args.rows) <= 0 or args.workers <= 0 or args.chunked_rows < 0:
        parser.error("rows and workers must be positive")
    checks = []
    with TemporaryDirectory(prefix="forge-stress-") as directory:
        backend = DuckDBBackend(replace(settings, backend="duckdb", homelab_directory=directory))
        backend.ensure_lakehouse()

        def healthy():
            status = backend.health()
            assert status[0], status
            return status

        for count in args.rows:
            def ingest(count=count):
                started = perf_counter()
                events = run_pipeline([SAMPLE_LOGS[index % len(SAMPLE_LOGS)] for index in range(count)], source_id=f"scale-{count}")
                parsed_at = perf_counter()
                try:
                    result = backend.ingest_events(events)
                except Exception:
                    for table in ("raw_events", "application_logs", "quarantine_events"):
                        assert backend.execute(f"SELECT count(*) FROM {table} WHERE source_id=?", [f"scale-{count}"])[1] == [[0]]
                    assert backend.execute("SELECT status FROM ingestion_runs WHERE source_id=?", [f"scale-{count}"])[1] == [["FAILED"]]
                    raise
                assert result.committed == count, result
                inserted_at = perf_counter()
                replay = backend.ingest_events(events)
                assert replay.duplicates == count and replay.committed == 0, replay
                return {"committed": count, "replayed": count,
                        "parse_seconds": round(parsed_at - started, 3),
                        "insert_seconds": round(inserted_at - parsed_at, 3),
                        "replay_seconds": round(perf_counter() - inserted_at, 3)}
            checks.append(measure(f"ingest-and-replay-{count}", ingest))
            checks.append(measure(f"recovery-{count}", healthy))

        if args.chunked_rows:
            def chunked():
                committed = 0
                for offset in range(0, args.chunked_rows, 10000):
                    count = min(10000, args.chunked_rows - offset)
                    events = run_pipeline([SAMPLE_LOGS[i % len(SAMPLE_LOGS)] for i in range(count)],
                                          source_id="sustained", source_offset_start=offset)
                    result = backend.ingest_events(events)
                    assert result.committed == count, result
                    committed += result.committed
                assert backend.execute("SELECT count(*) FROM raw_events WHERE source_id='sustained'")[1] == [[committed]]
                return {"committed": committed, "events_per_commit": 10000}
            checks.append(measure("sustained-chunked-ingestion", chunked))

        def large_records():
            events = run_pipeline([json.dumps({"message": "x" * (512 * 1024), "timestamp": "2026-09-10T00:00:00Z"})] * 48, source_id="large")
            result = backend.ingest_events(events)
            assert result.committed == 48, result
            return {"committed": 48, "payload_mib": 24}
        checks.append(measure("24-MiB-large-records", large_records))

        def concurrency():
            events = run_pipeline(SAMPLE_LOGS * 125, source_id="concurrent-stress")
            queries = {name: getattr(sql, name) for name in (
                "OVERVIEW_QUERY", "RECENT_QUERY", "SEVERITY_QUERY", "SERVICE_QUERY", "QUALITY_QUERY", "RUNS_QUERY", "WAREHOUSE_QUERY",
            )}

            def session(index):
                local = DuckDBBackend(backend.config)
                result = local.ingest_events(events)
                assert len(local.query_many(queries)) == len(queries)
                return result
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                results = list(pool.map(session, range(args.workers)))
            assert sum(r.committed for r in results) == len(events), results
            assert sum(r.duplicates for r in results) == len(events) * (args.workers - 1), results
            return {"sessions": args.workers, "unique": len(events)}
        checks.append(measure("concurrent-ingestion-and-dashboard", concurrency))

        def consistency():
            _, rows = backend.execute("SELECT (SELECT count(*) FROM raw_events), (SELECT count(*) FROM application_logs), (SELECT count(*) FROM quarantine_events)")
            raw, normalized, quarantine = rows[0]
            assert raw == normalized + quarantine, rows
            assert backend.health()[0]
            return {"raw": raw, "normalized": normalized, "quarantine": quarantine}
        checks.append(measure("final-integrity", consistency))
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
