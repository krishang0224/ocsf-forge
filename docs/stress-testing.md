# Stress and recovery audit — September 10, 2026

This is a bounded development audit, not a claim that every possible failure has been tested. The machine was an Intel Core i5-12450H, 16 GB RAM, Linux x86-64, with other desktop applications running and approximately 5 GB initially available. Python was 3.11.15; DuckDB was 1.5.5. Timing observations are single runs, not statistically controlled benchmarks or Raspberry Pi results.

The Trino 483 / Lakekeeper / MinIO / PostgreSQL stack used new, isolated test volumes. A temporary override limited Trino to a 2 GB Java heap, 3 GB container memory and two CPUs; the repository's normal 4 GB heap was not changed. Kafka 4.3.1 used a 384 MB heap for this audit. No production data was involved.

## What passed, and where it failed

| Workload | Observed result |
| --- | --- |
| DuckDB 50,000-event transaction and replay, 256 MB engine limit | Passed; 7.64 s insert, 6.70 s replay in the optimized scale run |
| DuckDB 100,000-event transaction | Out of memory at both 256 MB and 512 MB; no partial event rows, failed audit entry recorded, subsequent reads and writes worked |
| DuckDB sustained 250,000 events in 10,000-event transactions | Passed in 84.27 s including parsing; about 604 MiB peak process RSS during this run, despite the 256 MB engine limit |
| DuckDB 24 MiB document payload, 48 large records | Passed |
| Eight DuckDB sessions ingesting the same 1,000 events and loading all dashboard queries | Exactly 1,000 committed and 7,000 duplicates |
| DuckDB process termination between raw and normalized writes | Previously committed rows survived; incomplete transaction disappeared; replay committed exactly once |
| Real DuckDB memory exhaustion inside a write transaction | All event writes rolled back; audit recorded failure; next batch succeeded |
| Trino 2,500 / 10,000 events plus replay | Passed in 20.78 / 84.66 s respectively, including parsing and replay |
| Three simultaneous Trino writers, same 1,000 events | Real commit conflicts retried; 1,000 unique stored events and 2,000 duplicates reported |
| Trino partial commit interruption | Replay filled normalized records without duplicating raw evidence |
| Trino timestamp binding | `123456` microseconds and `+05:30` source offset round-tripped correctly |
| Live detections | All three rules, deterministic replay, evidence references and permission denials passed |
| Kafka outage recovery | 1,500 raw, 1,350 normalized, 150 quarantined; 150 unique dead letters. Committed offset stayed at 1,000 while Trino was paused with 500 pending messages, then advanced to 1,500 after recovery |
| Maintenance | Compaction and retention procedures completed across all five tables |
| Generated malformed-field corpus | 100,000 records completed without aborting the batch |
| JSON arrays, multiline CSV, XML and LEEF | 20,000 records per format parsed successfully |
| Million-record tiny JSONL document with a 50,000-event budget | Rejected before normalization in 0.075 s; approximately 100 MiB peak process RSS |

The atomic transaction limit is not a database row-count limit. Smaller commits successfully grew the database beyond 250,000 events. There is no automatic memory increase or partial-commit fallback. Full process memory includes Python records, serialized values, pandas and Streamlit caches; DuckDB's engine setting does not bound all of those allocations.

Final validation passed 227 tests with the live integration enabled (one isolated-environment-only check skipped), plus 48 tests in a homelab-only environment (two full-driver checks skipped). Lint, dependency consistency and all-profile Compose validation passed. Real browser checks covered homelab sample ingestion, record-budget rejection, malformed-neighbor quarantine, both SQL workspaces and CSV downloads. Both apps loaded without application exceptions; services were stopped after validation.

## Bugs and optimizations found

- JSON could decode an unpaired surrogate into a Python string that storage drivers cannot encode. One malformed event could abort its valid neighbors; document ingestion could also fail during UTF-8 hashing. Invalid escapes now enter quarantine with the original raw input. Duplicate-key diagnostics are safe to encode too.
- Syslog's unanchored key expression repeatedly scanned the suffix of long words without `=`. Its quoted-value alternatives also overlapped on backslashes. Restricting key starts and making escape alternatives disjoint removed these paths. A 20 KB plain message previously took 1.82 s; after the fix a larger 1 MB message completed in 0.024 s. A 100,000-backslash malformed value completed in 0.005 s. A subprocess timeout regression covers both, without imposing a fragile millisecond assertion.
- Stripping every quote from both ends of a Syslog value could remove an escaped final quote. Only the enclosing pair is removed now.
- A byte-only upload budget admitted millions of tiny records. UI and CLI now also check a record budget before normalization, without silently truncating input. CSV embedded newlines and Log4j stack continuations count as part of their logical event.
- DuckDB inserts expanded one placeholder per cell. Binding column lists instead reduced a 10,000-event insert from 4.31 to 1.27 s and replay from 3.62 to 1.01 s in the comparison run. Primary keys, bound values, timestamps and atomicity are retained. Disabling insertion-order preservation did not solve the 100,000-event memory failure, so that speculative tuning change was not adopted.
- SQL downloads now avoid rerunning the app and use a DuckDB filename in homelab mode.

## Reproduce safely

Install the appropriate requirements in a disposable environment. The homelab harness creates and removes its own temporary database; it does not use your configured storage directory:

```bash
pip install -r requirements-homelab.txt
python -m benchmarks.homelab --rows 2500 10000 25000 50000
python -m benchmarks.homelab --rows 2500 --chunked-rows 250000
```

`python -m benchmarks.homelab` additionally attempts the 100,000-event transaction. It reports failures as failures and exits nonzero if a case fails, even when recovery succeeds. Watch available memory; increasing `--rows` is not a safe way to determine physical-machine limits. Output is JSONL with durations and Linux peak RSS in KiB. The 24 MiB case and eight-session concurrency case are included in each run. The large-record case uses repeated content, not an incompressible-payload guarantee.

For the lakehouse, use a fresh Compose project and isolated volumes, never an existing deployment:

```bash
docker compose -p forge-stress up --build -d
pip install -r requirements-dev.txt
python -m benchmarks.lakehouse --confirm-test-stack --host localhost
ULPF_RUN_LIVE_TESTS=1 pytest -q tests/test_detection_live.py
docker compose -p forge-stress down
```

Do not run two stacks on the default ports. Use a temporary resource override on constrained hosts; the audit's heap differs from the default Compose configuration. The lakehouse harness uses unique source IDs and deletes only its own event/audit rows in `finally`; Iceberg history and files can remain until retention. Stop the test services afterward. Delete test volumes only after verifying the exact project and that they contain no data you need.

The Kafka outage and browser checks were performed live during this audit; they are not automated by the two harnesses above. CI runs the deterministic parser/backend/UI regressions, including local memory exhaustion and process-crash recovery. It does not reproduce these load timings or start the entire stack.

## Remaining limits

This did not test physical Pi hardware, long-duration soak workloads, abrupt host power loss, disk-full recovery, distributed object-storage failures, hostile multi-tenant access, or production TLS/authentication deployment. The homelab SQL console is for trusted local users, not an internet-facing sandbox. JSON/XML decoding still builds document structures in memory; the event budget is not a general memory sandbox.

DuckDB documents [index-memory limitations](https://duckdb.org/docs/current/guides/performance/indexing) and [larger-than-memory workload limits](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads). The measured failures here are why the project recommends small complete input batches instead of advertising unlimited ingestion.
