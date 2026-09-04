# Operations and recovery

## Persistence and backups

`minio-data` holds Parquet and Iceberg metadata objects. `catalog-data` holds Lakekeeper's PostgreSQL state. Both are required for a usable restore, so back them up at a coordinated recovery point and test restores regularly. Kafka data is persisted separately in `kafka-data` when the streaming profile is enabled.

Normal `docker compose down` does not delete these volumes. Never use `down --volumes` as a routine restart command.

## Ingestion recovery

Iceberg commits are atomic per table, but one ULPF run touches raw, normalized/quarantine, and run metadata tables. A process can fail between those commits. Recovery is safe because every event ID is deterministic and every table uses `MERGE ... WHEN NOT MATCHED`; replay the same source identity and offsets to fill any missing table without duplicating completed rows.

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
