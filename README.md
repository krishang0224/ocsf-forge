# ULPF Lakehouse

ULPF is a universal log processing pipeline for security and operations data. It accepts mixed vendor formats, preserves the original evidence, validates and normalizes successful records to OCSF 1.8 fields, and stores queryable Apache Iceberg tables behind Trino.

## What it solves

Security teams should not need a different storage schema and downstream query for every log source. ULPF separates source-specific parsing from a stable normalized contract:

```text
Files / paste / Kafka
JSON · CSV · XML · CEF · LEEF · Syslog · Apache · Log4j
                         │
                         ▼
             versioned parser registry
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       raw_events (bronze)   quarantine_events
              │              parser/validation errors
              ▼
      application_logs (silver, OCSF 1.8)
              │
              ▼
        Trino SQL and dashboard

Iceberg metadata ── Lakekeeper ── PostgreSQL
Parquet objects  ───────────────── MinIO
```

Every input record is written to `raw_events`. Valid records are merged into `application_logs`; invalid records retain their raw payload and error details in `quarantine_events`. `ingestion_runs` records counts, status, snapshot ID, and failures for each write attempt.

## Capabilities

- Versioned, confidence-based parsers for JSON objects, CSV files, XML events, CEF, LEEF, RFC 3164 and RFC 5424 Syslog, Apache Common/Combined logs, and multiline Log4j events.
- Lossless CEF extension parsing for values containing spaces and escaped CEF header delimiters.
- OCSF 1.8 category, class, activity, type, severity, and status identifiers.
- Timestamp validation with original text, timezone offset, observation time, and microsecond precision preserved separately. Invalid timestamps are quarantined rather than replaced with the current time.
- Deterministic event IDs from source identity, source offset, and payload hash. Iceberg `MERGE` makes a retry safe after a timeout or partial multi-table write.
- Bounded interactive uploads and an optional Kafka micro-batch worker for sustained ingestion with manual offset commits and a dead-letter topic.
- A durable Lakekeeper REST catalog backed by PostgreSQL and persistent MinIO, catalog, and Kafka volumes.
- Metric-gated Iceberg compaction plus snapshot and orphan-file retention jobs.
- Separate writer, dashboard, and analyst identities enforced by Trino file-based authorization. The analyst cannot read raw/quarantine evidence or mutate tables.

## Start the base stack

Requirements: Docker Compose or Podman Compose.

```bash
cp .env.example .env
docker compose up --build -d
```

Open:

- ULPF: <http://localhost:8501>
- Trino: <http://localhost:8080>
- MinIO console: <http://localhost:9001>
- Lakekeeper API: <http://localhost:8181>

All published ports bind to loopback. The application creates and evolves the four Iceberg tables once per Streamlit session. Named volumes keep objects and catalog state across normal container recreation:

```bash
docker compose down
docker compose up -d
```

`docker compose down --volumes` permanently removes the local warehouse and catalog database; use it only when deliberately resetting the environment.

## Ingest files and batches

Use the Sample, Upload, or Paste mode in the sidebar. Upload mode recognizes `.json`, `.jsonl`, `.csv`, `.xml`, `.log`, and `.txt`. The interactive path defaults to a 25 MB limit so a browser rerun cannot accidentally reparse an unbounded file.

For larger or continuous feeds, start Kafka and the worker:

```bash
docker compose --profile streaming up --build -d
```

Produce newline-delimited events to `localhost:9092`, topic `raw-app-logs`. The worker consumes bounded micro-batches, derives identity from topic/partition/offset, writes Iceberg first, publishes invalid records to `ulpf-dead-letter`, and then commits Kafka offsets.

## Run automatic maintenance

```bash
docker compose --profile operations up --build -d
```

The maintenance worker checks file count and average size before compacting. It always applies the configured snapshot and orphan-file retention windows. Defaults are conservative and configurable in `.env`:

```dotenv
ULPF_COMPACTION_MIN_FILES=50
ULPF_COMPACTION_TARGET_MB=128
ULPF_SNAPSHOT_RETENTION_DAYS=7
ULPF_ORPHAN_RETENTION_DAYS=7
ULPF_MAINTENANCE_INTERVAL_SECONDS=86400
ULPF_MAINTENANCE_TABLES=raw_events,application_logs,quarantine_events,ingestion_runs
```

See [operations.md](docs/operations.md) before changing retention or recovery settings.

## Security model

The browser SQL workspace is constrained twice: application validation permits one read-only statement and caps displayed rows, while Trino independently limits `ulpf_reader` to normalized events and ingestion-run metadata. `ulpf_dashboard` has read access to monitoring tables; `ulpf_writer` owns ingestion and maintenance.

The bundled stack is a loopback-only development deployment. Lakekeeper intentionally runs without OIDC so local startup requires no external identity provider. Before exposing any endpoint, follow [production-security.md](docs/production-security.md) to add TLS, OIDC, secret-managed scoped credentials, network policy, and backups.

## Develop and test

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
ruff check .
docker compose config --quiet
```

The suite covers parser behavior, timestamp validation, OCSF fields, structured uploads, multiline records, deterministic IDs, SQL guards, bound parameters, connection reuse, and maintenance decisions. The real stack has also been exercised for Iceberg writes, replay deduplication, quarantine routing, timestamp round trips, access denial, catalog restart persistence, Kafka ingestion, dead-letter delivery, and maintenance procedures.

To add a vendor format without changing pipeline or UI code, follow [parser-development.md](docs/parser-development.md).
