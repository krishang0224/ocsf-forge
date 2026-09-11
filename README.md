# OCSF Forge

[![CI](https://github.com/krishang0224/ocsf-forge/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/krishang0224/ocsf-forge/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](CONTRIBUTING.md)

**Mixed logs in. Queryable OCSF out.**

OCSF Forge turns JSON, CSV, XML, CEF, LEEF, Syslog, Apache, and Log4j records into one security-event model. It keeps the original evidence, sends bad records to quarantine, and writes the clean stream to Apache Iceberg for SQL analysis through Trino.

An optional detection worker identifies repeated authentication failures, possible password spraying, and successful logons after repeated failures. Findings include the triggering rule and source event IDs for investigation.

The project exists for a familiar reason: collecting logs is easy; making eight incompatible formats useful in the same query is not.

![Terminal-theme dashboard showing stored event totals, severity distribution, services, and recent events](docs/images/dashboard.png)

Screenshots captured from the running app on September 9, 2026, using retained bundled samples and the synthetic authentication demo. Counts and quarantine rates reflect that historical demo data, not a fresh run or a throughput benchmark. [Why OCSF?](docs/why-ocsf.md)

[Evaluation guide and verification checkpoint](docs/evaluation.md) · [Contribute a parser](docs/parser-development.md)

<details>
<summary>SQL workspace and ingestion results</summary>

![Terminal-theme SQL workspace querying three authentication findings from Iceberg](docs/images/sql-workspace.png)

![Ingestion quality showing parser coverage and historical completed and quarantined demo runs](docs/images/ingestion.png)

</details>

## See the pipeline work

```text
files / paste / Kafka
        |
        v
JSON / CSV / XML / CEF / LEEF / Syslog / Apache / Log4j
        |
        v
versioned parser registry
        |
        +-- raw_events          original evidence
        +-- quarantine_events   rejected data + reason
        +-- application_logs    normalized OCSF 1.8 events
                    +-- authentication rules --> detections
                    |
                    v
             Trino SQL + dashboard

Iceberg catalog  -> Lakekeeper + PostgreSQL
Parquet storage  -> MinIO
```

Every record gets a deterministic ID from its source, offset, and payload hash. Replaying a file or Kafka range fills incomplete writes without duplicating rows.

## Run locally

### Try the core without Docker

From a checkout, with Python 3.11. These commands use only the Python standard library—no dependency install or services needed:

```bash
python -m ulpf demo
python -m ulpf normalize your-logs.jsonl > normalized.jsonl
```

The synthetic demo prints three findings, including their rule IDs and supporting event IDs. It uses the same parser and rule code as the lakehouse, but does not connect to storage. Normalization writes accepted OCSF records to stdout and rejection diagnostics plus a summary to stderr. Exit codes: `0` no rejections (including empty input), `1` rejected records present, `2` input/usage error. Input is bounded to 25 MiB and 50,000 events by default (`--max-bytes` / `--max-events`); this is a batch evaluator, not a streaming substitute. Keep the source file: the CLI does not persist quarantine or raw evidence.

### Run the dashboard without Docker

[Homelab mode](docs/homelab-mode.md) stores raw, normalized, and quarantined events in a local DuckDB file. Install `requirements-homelab.txt` in a clean environment, explicitly set `ULPF_BACKEND=duckdb`, and start Streamlit. It has no external services, Kafka worker, or scheduled detection worker. Trino remains the default; a failed connection never activates DuckDB.

### Start the full lakehouse

You need Docker Compose or Podman Compose. The first launch downloads several images and builds the app; allow extra time for your connection and laptop. Later launches reuse cached images. The local Trino configuration reserves a 4 GB Java heap, in addition to the other services.

```bash
cp .env.example .env
docker compose up --build -d
```

Open [localhost:8501](http://localhost:8501), choose Sample, Upload, or Paste, and commit the batch. The dashboard shows parser quality, quarantine counts, ingestion runs, and Iceberg file health.

Both dashboards limit interactive input to 25 MiB and 50,000 events before normalization. `ULPF_MAX_UPLOAD_BYTES` and `ULPF_MAX_UPLOAD_EVENTS` configure those limits; raising them also raises memory risk. Rejected oversized input is not ingested or silently truncated.

Useful local endpoints:

| Service | URL |
| --- | --- |
| OCSF Forge | <http://localhost:8501> |
| Trino | <http://localhost:8080> |
| MinIO console | <http://localhost:9001> |
| Lakekeeper API | <http://localhost:8181> |

All ports bind to loopback. Named volumes keep the warehouse, catalog, and Kafka state when containers are recreated. `docker compose down --volumes` deletes that state permanently.

## Make the workspace yours

Terminal is the default: compact spacing, monospace text, sharp corners, and no glow. Open the collapsed **Appearance** sidebar panel for Solarized, High Contrast, Cyberpunk, or Custom. Custom controls cover accent/background, font, density, corners, glow, and scanlines. Settings survive reruns and can be shared by copying the browser URL.

<details>
<summary>Preview the appearance controls</summary>

![Custom appearance controls alongside the dashboard, retaining the compact Terminal palette](docs/images/appearance.png)

</details>

Native table canvases and charts do not fully inherit per-session CSS changes. See [appearance controls and tradeoffs](docs/appearance.md).

## What is already handled

- CEF extension values containing spaces and escaped delimiters
- Apache Common and Combined formats
- RFC 3164 and RFC 5424 Syslog
- multiline Log4j stack traces in files, pasted input, or one complete Kafka message
- JSON arrays, CSV files, and XML event collections
- timezone-aware timestamps with microsecond precision
- invalid timestamps, IP addresses, and ports routed to quarantine
- OCSF 1.8 class, category, activity, type, severity, and status IDs
- concurrent Iceberg commit conflicts with bounded retry
- duplicate-safe replay after a timeout or partial write
- separate Trino permissions for ingestion, dashboards, and analysts

Adding a parser does not require changing the pipeline or UI. See [parser development](docs/parser-development.md).

## Measured, not guessed

Latest stress audit: **September 10, 2026**, on an Intel Core i5-12450H with 16 GB RAM. These are single-run development observations, not production capacity promises or Raspberry Pi benchmarks. Trino used a temporary 2 GB heap and two-CPU limit for this audit; the normal deployment defaults were not changed.

| Check | Result |
| --- | ---: |
| Homelab sustained ingestion | 250,000 events in 10,000-event commits; 84.27 seconds including parsing |
| Homelab 50,000-event transaction | 7.64 seconds to insert; 6.70 seconds to replay |
| Eight homelab sessions, same input | 1,000 unique events; 7,000 duplicates detected |
| Trino 10,000-event ingestion and replay | 84.66 seconds combined |
| Three concurrent Trino writers | 1,000 unique events; real commit conflicts retried |
| Kafka outage recovery | 1,500 raw events accounted for; offsets held during the outage |
| Invalid Kafka records | 150 quarantined; 150 unique dead letters |
| Failure recovery | DuckDB memory exhaustion/process termination and Trino partial-write replay passed |
| Automated checks | [Full-stack CI](https://github.com/krishang0224/ocsf-forge/actions/workflows/ci.yml) · [Homelab CI](https://github.com/krishang0224/ocsf-forge/actions/workflows/homelab.yml) |

**Known limit:** a single 100,000-event homelab transaction exhausted both the 256 MB and 512 MB DuckDB engine budgets. It rolled back without partial event rows, and subsequent reads and writes worked. Smaller complete batches succeeded; total database size and single-transaction size are different limits. The engine memory setting does not cap total Python/Streamlit memory.

The audit fixed malformed Unicode aborting batches, slow Syslog field scanning, escaped-quote loss, and byte-only input limits. Binding DuckDB inserts by column reduced a separate 10,000-event insert comparison from 4.31 to 1.27 seconds. Trino retains size-aware batching and idempotent conflict retries.

See the [full stress report and reproduction commands](docs/stress-testing.md) for methodology and untested scenarios. CI runs deterministic regressions, lint, and Compose validation; it does not reproduce these live load timings. Test counts remain in CI output rather than a fixed README claim.

## Stream from Kafka

```bash
docker compose --profile streaming up --build -d
```

Send newline-delimited events to `localhost:9092` on `raw-app-logs`. The worker writes Iceberg before committing Kafka offsets. Invalid records also go to `ulpf-dead-letter` with their source coordinates and error reason.

Kafka message boundaries are event boundaries. A complete multiline stack trace in one message is parsed as one event; a trace split across several messages remains several records because the worker does not guess where a cross-message trace ends.

## Detect suspicious authentication

```bash
docker compose --profile detection up --build -d
docker compose exec -T app python -m ulpf.detection.demo > /tmp/ocsf-detection-demo.jsonl
```

Upload the generated file and ingest it. The 15 synthetic events produce three local findings with default thresholds; open **Findings** and refresh after the next scan. Each finding is an investigation lead, not a verdict. [Rules, tuning, replay limits, and backfills](docs/detection.md).

Select a finding and choose **Load supporting events** to inspect its normalized evidence without copying IDs into SQL. Missing retained evidence is reported explicitly.

![Terminal-theme Findings view with three authentication alerts, selected rule, and source evidence IDs](docs/images/detections.png)

## Operate it

```bash
docker compose --profile operations up --build -d
```

The operations worker compacts small Iceberg files and applies snapshot and orphan-file retention. Read [operations and recovery](docs/operations.md) before changing retention values.

The browser SQL workspace accepts one read-only statement and fetches at most 1,000 rows by default. Trino enforces table permissions independently, so the analyst identity cannot read raw or quarantined evidence.

## Where AI fits

No language model sits in the ingestion path. Parsing, validation, IDs, and OCSF mapping are deterministic, which keeps results reproducible and auditable. The normalized tables are suitable input for downstream anomaly detection, clustering, incident summaries, or other ML-assisted analysis without making model output part of the evidence record.

## Honest limits

- The bundled deployment is for a loopback-only development machine, not an internet-facing production cluster.
- Generic formats work today; deep vendor coverage still requires vendor-specific parser modules and fixtures.
- A single event larger than the safe Trino binding limit is rejected before event tables are partially written. Very large payloads should be stored externally and referenced by URI.
- Multi-table ingestion is recoverable and idempotent, but not one atomic transaction across every Iceberg table.
- Structured uploads are split into extracted records: JSON, CSV, and XML formatting is not retained byte for byte. Archive the original file separately if whole-document forensic preservation is required.
- Duplicate JSON keys, non-finite JSON numbers, ambiguous CSV headers, malformed CSV rows, and invalid UTF-8 are rejected. An invalid CSV document is quarantined as a whole rather than partially accepted.
- OCSF-aligned output is not a claim of complete schema validation or full vendor coverage. Local rules cover three authentication patterns, not a replacement for a SIEM or incident-response process.

Read the [production security checklist](docs/production-security.md) before exposing any service.

## Develop

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
ruff check .
docker compose --profile streaming --profile operations --profile detection config --quiet
```

The Python package remains named `ulpf` so existing deployments and environment variables continue to work after the project rename.

`ulpf/parsers.py` is a compatibility facade; implementations and registration live in `ulpf/parsing/`. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for new parsers and fixes. See the [changelog](CHANGELOG.md) before upgrading an existing deployment.

## License

Copyright 2026 krishang0224. Licensed under the [Apache License, Version 2.0](LICENSE). Dependencies and container images retain their respective licenses.
