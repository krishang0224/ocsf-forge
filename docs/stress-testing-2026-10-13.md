# Stress and recovery audit — October 13, 2026

This audit increased load until failures appeared, then tested the fixes and recovery. It used an Intel Core i5-12450H, 16 GB RAM, Linux x86-64, Python 3.11.15 and DuckDB 1.5.5. About 5.8 GB RAM was initially available with desktop applications running. Some diagnostics and workloads overlapped, and swap was used. Timings are individual development observations, not controlled capacity benchmarks.

DuckDB used temporary databases and a 256 MB engine budget. Python stress processes ran in scopes with explicit memory limits and swap disabled. The live stack used new volumes in Compose project `forge-stress-20261013`: Trino 483 with a temporary 2 GB heap, 3 GB container limit and two CPUs; MinIO/Lakekeeper/PostgreSQL had separate container limits. Kafka 4.3.1 used a 384 MB heap and 768 MB container limit. The normal deployment still uses its existing 4 GB Trino heap.

## Results and boundaries

| Workload | Observed result |
| --- | --- |
| DuckDB 25,000-event transaction and replay | Passed; 1.37 s parsing, 3.44 s insertion, 2.71 s replay |
| DuckDB 50,000-event transaction and replay | Passed; 2.50 s parsing, 6.26 s insertion, 5.00 s replay |
| DuckDB 100,000-event transaction | Engine memory exhausted at 256 MB; no partial event rows, failed audit row recorded, next reads worked |
| DuckDB sustained ingestion | 500,000 events in 10,000-event transactions; 147.39 s including parsing |
| Sixteen DuckDB ingestion/dashboard sessions with identical input | 1,000 committed; 15,000 duplicates; all dashboard queries worked |
| Final DuckDB integrity | 576,048 raw and normalized rows; no quarantine rows or unexplained partial rows |
| Large DuckDB records | 48 records totaling 24 MiB accepted; 1.35 s; repeated content, not an incompressible-data test |
| Mixed-format parsing | 250,000 events passed in a 1.5 GiB scope; 500,000 exceeded that scope and was killed |
| Mixed-format parsing with a 2 GiB scope | 500,000 passed in 34.94 s; child process peak RSS about 1.79 GiB |
| Malformed structured corpus | 100,000 records completed without aborting; 98,205 quarantined; 5.28 s |
| JSON array / CSV / XML documents | 50,000 accepted records each; 2.20 / 2.00 / 4.39 s respectively |
| Million-record JSONL with a 50,000-event budget | Rejected before normalization; the combined record-budget/deep-XML probe completed in 0.105 s |
| Large plain Syslog messages | 0.5 / 2 / 8 MB completed in about 0.014 / 0.056 / 0.228 s |
| Detection cardinality | 100,000 events each for one user, password spraying and distinct sources; expected finding counts, no batch failure |
| Trino with original history defaults | 10,000-event ingestion/replay passed in 79.46 s; the following 25,000-event run exhausted Java heap and restarted the coordinator |
| Recovery after that real Trino failure | Raw table had 25,000 rows; normalized table had 18,816. Replay inserted exactly the missing 6,184 and preserved 25,000 distinct IDs in both tables; 131.98 s |
| Full replay after recovery | 25,000 duplicates and no new normalized rows; 289.06 s with other checks overlapping |
| Fresh Trino ingestion/replay after history tuning | 25,000 committed and 25,000 replay duplicates; 404.06 s; no coordinator restart |
| Three simultaneous Trino writers | 1,000 distinct rows, 2,000 duplicates; real commit conflicts retried; 36.26 s |
| Trino timestamp / malformed neighbor | Microseconds `123456` and source offset `+05:30` preserved; valid record committed and invalid record quarantined |
| Kafka storage outage | Offset held at 4,000 while Trino was paused with 1,000 more messages pending, then advanced to 5,000 |
| Kafka accounting | 5,000 unique raw rows, 4,500 normalized, 500 quarantine and 500 unique dead letters; 111.58 s including initialization and a five-second pause |
| Live detections | All three rules, replay, evidence references and permission denials passed |
| Live watchdog | Detected an intentionally old RUNNING row; the synthetic row was then removed |
| Dashboard and SQL | Seven-query bundle passed; Streamlit runtime test rendered live dashboard, preview, findings and SQL without application errors |
| Maintenance/compaction | Raw files 982 → 7, normalized files 1,557 → 7, audit files 103 → 1; row/distinct-ID counts unchanged. Dashboard bundle 5.40 s before and 0.84 s after; one warm-cache comparison |

The first parser run exited with signal-related status 137 when it reached its process memory cap. Increasing that explicit test scope to 2 GiB allowed the same 500,000-record workload to finish. This does not change the 50,000-event UI/CLI default or provide an automatic memory increase. The API can materialize large batches when its caller omits a budget; callers should supply one. Process RSS, engine memory and cgroup memory accounting are different measurements.

The failed 100,000-event DuckDB case makes its harness exit nonzero even though rollback and later cases succeed. A total database exceeding half a million rows does not imply that a transaction of that size will fit. Atomic batches are never silently split.

## Changes supported by the failures

**XML depth:** ElementTree could parse a deeply nested document, but document serialization recursively visited it and raised an uncaught `RecursionError`. Shared decoding now caps nesting at 256 elements before serialization. Uploads and direct event parsing apply the same budget and retain rejected input for quarantine. XML parser version is `1.2.2`. Tests cover 2,000 levels, the exact depth boundary, raw hashes and valid neighbors. This is an explicit input restriction; it is not a complete XML resource sandbox.

**Preview conversion:** the UI converted every field with recursive dataclass copying and only then selected the displayed columns. That copied hidden metadata unnecessarily. It now requests those columns directly. A synthetic 1,000-row batch with 10,000 extra integers per record took 6.80 s through full conversion versus 0.00105 s through projection, with identical selected values. This constructed normalized batch bypasses the upload byte cap and isolates conversion cost; it is not typical-upload latency. Full export behavior is preserved. The regression checks that hidden fields are not copied.

**Missing IDs:** the live Trino API accepted a blank event ID. Deduplication cannot distinguish independent events with that identity. Both backends now reject missing, blank or non-string IDs before connecting; callers still provide deterministic identities. A new parameterized regression covers rejection before any Trino writes. The synthetic blank-ID row used to establish the bug was removed.

**Coordinator history:** immediately before the heap failure, Trino retained 263 queries and approximately 88 MiB of query text; the active query reported about 9 MiB of execution memory. Logs showed repeated major collections recovering almost no heap, followed by Java heap exhaustion. Retained text is only part of the associated query/plan memory. Shortening history is consistent with this diagnosis: recovery, full replay, the fresh 25,000-event run and subsequent checks completed with the same heap and no new restart. This is evidence of improved survival for these workloads, not a heap-allocation proof or a throughput promise.

Compose now supplies `TRINO_QUERY_HISTORY_MAX=20` and `TRINO_QUERY_HISTORY_MIN_AGE=30s`. The count is not a hard immediate ceiling: queries younger than the minimum age can remain beyond it. This shortens Trino Web UI diagnostics; Iceberg snapshots, raw records and ingestion audit tables are unaffected. Use external query-event logging or increase these values when longer diagnostics are needed. See [Trino's property definitions](https://trino.io/docs/483/admin/properties-query-management.html#query-max-history).

**Audit harnesses:** the lakehouse harness's cleanup exception could obscure the original storage failure when the server was down. It now reports cleanup failures separately and attempts every owned source/table. The new pipeline harness can isolate workloads in children and continue after a child failure or timeout. A new streaming harness reproduces the offset/outage/dead-letter checks using unique topics and a managed worker process.

**Build context:** the local validation cache occupied 23 MiB and was ignored by Git but still included in Docker's build context. Container builds now exclude that cache, build/distribution artifacts, package metadata and coverage output. The local cache is preserved for offline checks.

## Reproduce

Install application, homelab and test dependencies in Python 3.11. Run workload processes with an appropriate explicit OS memory limit; on this Linux machine, scopes used `systemd-run --user --scope -p MemoryMax=2G -p MemorySwapMax=0` before the command. These settings protect the test process budget but do not make a busy desktop a controlled benchmark.

```bash
python -m benchmarks.homelab --rows 25000 50000 100000 --workers 16 --chunked-rows 500000
python -m benchmarks.pipeline --rows 500000 --isolate
```

For live tests, use an isolated Compose project and verify the exact container names and available ports first. The normal configuration has the new history defaults; the original failure was measured before adding them. Reproducing this audit's smaller heap requires a temporary resource/JVM override.

```bash
docker compose -p forge-stress --profile streaming up --build -d
python -m benchmarks.lakehouse --confirm-test-stack --host localhost --rows 25000
python -m benchmarks.streaming --confirm-test-stack --trino-container forge-stress-trino-1 --messages 5000
ULPF_RUN_LIVE_TESTS=1 pytest -q tests/test_detection_live.py
docker compose -p forge-stress --profile streaming down
```

For Podman, use its Compose implementation, pass `--runtime podman` to the streaming harness and supply the container name returned by `podman ps`. The streaming harness creates unique topics and leaves synthetic evidence in the disposable stack. Cleanup attempts to resume its selected Trino container and stops its worker even if the resume command fails. The lakehouse harness deletes only its own source rows, unless the backend is unavailable; its printed source prefix permits later inspection/recovery. No harness should target a production deployment.

Before publication, the full prepared-toolkit suite passed 323 tests with two environment-specific checks skipped; the live detection test passed separately. Lint, the exact OCSF fixture gate and all-profile Compose validation passed. The gate still has seven valid fixtures and the explicitly expected missing-endpoint CSV failure.

All test services were stopped afterward; isolated test volumes were preserved. This run did not fill the host disk or test host power loss, distributed storage faults, production authentication, or physical Raspberry Pi hardware. CSV still uses its standard 131,072-character field budget; the 512 KiB ASCII-field probe was quarantined cleanly. Large commits, repeated content and short synthetic workloads are not substitutes for sizing a real deployment.
