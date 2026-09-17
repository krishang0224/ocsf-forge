# Operations and recovery

## Persistence and backups

`minio-data` holds Parquet and Iceberg metadata objects. `catalog-data` holds Lakekeeper's PostgreSQL state. Both are required for a usable restore, so back them up at a coordinated recovery point and test restores regularly. Kafka data is persisted separately in `kafka-data` when the streaming profile is enabled.

Normal `docker compose down` does not delete these volumes. Never use `down --volumes` as a routine restart command.

## Ingestion recovery

Iceberg commits are atomic per table, but one OCSF Forge run touches raw, normalized/quarantine, and run metadata tables. A process can fail between those commits. Recovery is safe because every event ID is deterministic and every table uses `MERGE ... WHEN NOT MATCHED`; replay the same source identity and offsets to fill any missing table without duplicating completed rows.

Kafka offsets are committed only after the Iceberg writes and dead-letter flush succeed. A crash therefore causes replay, which the same event IDs deduplicate.

Inspect recent state with:

```sql
SELECT *
FROM iceberg.logging.ingestion_runs
ORDER BY started_at DESC
LIMIT 100;
```

Runs left in `RUNNING` may represent a live slow writer or a process that stopped before final status was recorded. Confirm the writer has stopped before replaying the source; retain the original run row as audit evidence.

## Stale-run watchdog

The operations-profile maintenance process checks for `RUNNING` rows older than `ULPF_STUCK_RUN_TIMEOUT_SECONDS` (default 3600). `ULPF_WATCHDOG_INTERVAL_SECONDS` defaults to 300; both must be positive integers. It emits structured JSON with `event=stale_ingestion_runs`, up to 100 oldest run IDs and a `truncated` flag. Route that event to your alert system. Empty checks emit `ingestion_watchdog_ok`; query failures emit `ingestion_watchdog_error`, not a healthy result.

This is deliberately flag-only. Elapsed time is not proof of a dead writer, and a run row does not supply complete replayable source bytes or credentials. The watchdog does not change statuses, reclaim writers or retry ingestion. Inspect the process and replay the same source identity/offsets only when appropriate.

Checks share the maintenance process, so a long maintenance operation can delay them; the interval is not an alerting SLA. The existing container healthcheck checks process liveness, not data freshness. An external log-based monitor must also alert when watchdog messages stop. The watchdog applies to Trino, not the atomic DuckDB homelab path.

## Maintenance

The `operations` profile runs `ulpf.maintenance` once per configured interval. Compaction occurs only after both thresholds indicate a small-file problem. Snapshot expiration bounds metadata history and time travel. Orphan deletion has a hard minimum retention of three days in code; the Trino catalog also enforces its own minimum.

Align retention with incident-response and compliance requirements before shortening it. Pause maintenance during a coordinated restore or catalog migration.

## Compose verification scope

Podman Compose has been run end-to-end against this repository's full local stack, including ingestion and Kafka/Trino recovery in the [dated stress audit](stress-testing.md). It is not merely an assumed-compatible alternative. Docker Compose is checked for configuration validity in CI; that check is not an end-to-end Docker run. No minimum-version compatibility matrix has been established, and this change set does not claim a fresh live-stack boot.

## Monitoring

Alert on failed or stale ingestion runs, falling parser success rate, quarantine growth, Kafka consumer lag, unavailable Trino/Lakekeeper/MinIO health, excessive Iceberg data files, and backup age. The dashboard exposes parser quality, recent runs, snapshot count, file count, and average file size for initial operations.

With the detection profile enabled, also monitor successful scan timestamps, detector health, and scan-limit errors. Findings are stored separately in `detections`. See [detection operations](detection.md) for replay, retention, and backfill behavior.

## Ingestion tuning

`ULPF_INSERT_BATCH_SIZE` limits rows per Iceberg merge, while `ULPF_TRINO_MAX_QUERY_BYTES` also splits batches according to their encoded parameter size. Keep the latter below Trino's configured query-text limit; the default 850,000-byte safety ceiling is intended for the stock 1 MB limit. `ULPF_ICEBERG_COMMIT_RETRIES` controls bounded exponential backoff when concurrent writers conflict on an Iceberg partition. Read-only console results are fetched only up to `ULPF_QUERY_ROW_LIMIT`, rather than loading an unbounded result into application memory.

The local Trino container is capped at a 4 GB Java heap in `infra/trino/jvm.config`. Size this explicitly for production instead of inheriting the container default, which can reserve most of the host's memory.
