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

Runs left in `RUNNING` indicate that the process stopped before final status was recorded. Reprocess the source and retain the original run row as audit evidence.

## Maintenance

The `operations` profile runs `ulpf.maintenance` once per configured interval. Compaction occurs only after both thresholds indicate a small-file problem. Snapshot expiration bounds metadata history and time travel. Orphan deletion has a hard minimum retention of three days in code; the Trino catalog also enforces its own minimum.

Align retention with incident-response and compliance requirements before shortening it. Pause maintenance during a coordinated restore or catalog migration.

## Monitoring

Alert on failed or stale ingestion runs, falling parser success rate, quarantine growth, Kafka consumer lag, unavailable Trino/Lakekeeper/MinIO health, excessive Iceberg data files, and backup age. The dashboard exposes parser quality, recent runs, snapshot count, file count, and average file size for initial operations.

## Ingestion tuning

`ULPF_INSERT_BATCH_SIZE` limits rows per Iceberg merge, while `ULPF_TRINO_MAX_QUERY_BYTES` also splits batches according to their encoded parameter size. Keep the latter below Trino's configured query-text limit; the default 850,000-byte safety ceiling is intended for the stock 1 MB limit. `ULPF_ICEBERG_COMMIT_RETRIES` controls bounded exponential backoff when concurrent writers conflict on an Iceberg partition. Read-only console results are fetched only up to `ULPF_QUERY_ROW_LIMIT`, rather than loading an unbounded result into application memory.

The local Trino container is capped at a 4 GB Java heap in `infra/trino/jvm.config`. Size this explicitly for production instead of inheriting the container default, which can reserve most of the host's memory.
