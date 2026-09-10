# Homelab mode

Homelab mode uses the existing parsers, normalization pipeline, event IDs and OCSF export unchanged, with an embedded DuckDB database instead of external storage services. It is for local, modest-volume investigation—not a smaller distributed lakehouse.

**Explicit opt-in only.** The default remains `trino`. The full-stack requirements, Compose deployment and lakehouse workers remain available; no local-storage service is added to Compose. A failed Trino connection never activates DuckDB.

## Start without Docker

From a checkout, create a clean Python 3.11 environment:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements-homelab.txt
export ULPF_BACKEND=duckdb
export ULPF_HOMELAB_DIRECTORY="$HOME/.local/share/ocsf-forge"
streamlit run app.py --server.address 127.0.0.1
```

Open <http://localhost:8501>. Select Sample, Upload or Paste, then **Ingest into DuckDB**. The default sample produces eight normalized events. Repeating the same input reports duplicates without adding rows. The Current data view includes severity/service breakdowns, parser quality, quarantine counts, ingestion runs, and local storage size. SQL workspace and batch downloads use the same UI components as the full deployment.

Set environment variables in the shell or your service manager. Streamlit does **not** automatically source an `.env.homelab` file. On PowerShell, use `$env:ULPF_BACKEND="duckdb"` and `$env:ULPF_HOMELAB_DIRECTORY="C:\path\to\private-data"` before starting Streamlit.

The requirements contain Streamlit, pandas, Plotly and DuckDB, plus their transitive dependencies. No `trino`, `minio`, or `kafka-python` package is required. Installation needs package access; running the app needs no external service. For a Raspberry Pi, use a 64-bit OS and Python 3.11 with compatible Linux ARM64 wheels. This implementation has been tested on Linux x86-64, not on physical Pi hardware; do not infer a Pi throughput guarantee from desktop tests.

Generic parsing is unchanged: this does not introduce dedicated Pi-hole, WireGuard or NAS mappings. Inspect the normalized fields from your actual exports; unsupported formats still enter quarantine.

## Storage and operating model

- The directory contains `iceberg.duckdb` and, while needed, its `.wal` sidecar. This is **DuckDB's native format**, not Parquet or an Iceberg table. The filename retains the `iceberg` SQL catalog name so existing analytical queries can continue to use `iceberg.logging.application_logs`.
- Tables: `raw_events`, `application_logs`, `quarantine_events`, `ingestion_runs`, under the `logging` schema. Short names also work in the console. Trino catalog/schema/table environment variables do not rename the homelab schema.
- Event IDs have primary keys. Inserts use bound parameters and conflict-ignore semantics, preserving existing records on replay. Raw, normalized, quarantine and successful audit writes are in one atomic transaction. Failed batches roll back their event writes and attempt a separate failed-run audit entry.
- One Streamlit process owns a database. Threads/sessions in that process are serialized by database path. Other processes are subject to DuckDB file locks; do not run multiple writers or share the database over a network filesystem.
- Keep the directory private and outside Git. The database contains raw security logs and quarantine evidence. Stop the app before copying the directory for backup; retain any WAL sidecar. Backups are not a built-in snapshot/history feature.
- To return to the existing lakehouse path, stop Streamlit and unset `ULPF_BACKEND`, or set it to `trino` and use the existing deployment instructions. This does not import, convert or delete either backend's data.

## Resource controls

| Environment variable | Default | Effect |
| --- | --- | --- |
| `ULPF_BACKEND` | `trino` | Only `duckdb` selects this mode; unknown values fail clearly |
| `ULPF_HOMELAB_DIRECTORY` | `~/.local/share/ocsf-forge` | Private local storage directory |
| `ULPF_DUCKDB_MEMORY_LIMIT` | `256MB` | DuckDB execution memory limit, not a cap on total Python/Streamlit memory |
| `ULPF_DUCKDB_THREADS` | `2` | DuckDB worker threads |
| `ULPF_DUCKDB_QUERY_TIMEOUT` | `10` | Seconds before interrupting a console/dashboard query |
| `ULPF_QUERY_ROW_LIMIT` | `1000` | Maximum rows fetched by each read |
| `ULPF_INSERT_BATCH_SIZE` | `500` | Bound-parameter batch size inside a transaction |
| `ULPF_MAX_UPLOAD_BYTES` | `26214400` | Shared 25 MiB interactive input limit |
| `ULPF_MAX_UPLOAD_EVENTS` | `50000` | Shared interactive record limit, checked before normalization |

Large inputs still occupy Python memory during decoding and parsing. The record limit prevents millions of tiny records from expanding into normalized objects; it is not a process-memory cap. Row limits constrain results, not the amount of work required by a query; memory settings and query interruption provide additional bounds. Split large files on complete record boundaries.

The September 10 stress run passed 250,000 events as separate 10,000-event commits at the default engine limit. A single 100,000-event transaction failed at both 256 MB and 512 MB, rolled back, and left the database usable. Increasing the statement batch size or doubling memory is not a reliable fix for oversized transactions. Use smaller complete input documents; the backend never silently divides an atomic ingestion into separate commits. See [stress results and reproduction](stress-testing.md).

## Read-only console boundary

Every public DuckDB read method validates a single statement and uses a read-only database connection. Mutations, administrative statements, attachment, import/export, extension installation/loading and arbitrary local/network file reads are disabled. The backend explicitly loads only DuckDB's bundled ICU support for UTC timestamps; automatic extension loading/downloading is disabled. The trusted ingestion path alone opens a writable connection.

`ULPF_ALLOW_MUTATING_SQL=true` and `query(..., enforce_read_only=False)` do **not** bypass homelab safety. There is no homelab administrative SQL console. Unlike the Trino deployment, homelab does not implement separate database users/roles: the local user can query raw and quarantined evidence. This is a loopback-only, trusted-user tool, not an authenticated multi-tenant service or a sandbox for hostile SQL. Do not expose Streamlit directly to the internet.

## Exact dialect and behavior differences

| Area | Homelab adaptation |
| --- | --- |
| Schema DDL | Remove Iceberg `WITH (...)` format/partition properties; replace `TIMESTAMP(6) WITH TIME ZONE` with DuckDB `TIMESTAMPTZ`; add primary keys for event/run IDs |
| `OVERVIEW_QUERY` | Wrap the outer `count_if(...)` in `coalesce(..., 0)`, because DuckDB returns NULL on an empty input rather than Trino's zero |
| `RECENT_QUERY`, `SEVERITY_QUERY`, `SERVICE_QUERY`, `QUALITY_QUERY`, `RUNS_QUERY` | Execute unchanged; the shared `count_if`, `arbitrary`, and interval syntax are supported by the pinned DuckDB version |
| `WAREHOUSE_QUERY` | `query()`/`query_many()` substitute local database/WAL byte counts. Iceberg `data_files`, `average_file_mb`, and `snapshots` are NULL, not fabricated counts; the UI labels the view Local storage |
| SQL examples | Replace Iceberg snapshots with Local tables; omit local-worker findings. Other examples are unchanged; arbitrary user SQL is DuckDB SQL, not automatically translated Trino SQL |
| Timestamp display | UTC microsecond timestamps retain the source instant; original source text and offset remain separate columns. OCSF interchange keeps its existing millisecond representation |
| Transactions/replay | One atomic local transaction across event tables, rather than separate recoverable Iceberg table commits; primary keys enforce uniqueness |
| Parameter binding | Local inserts bind one list per column and expand them with `unnest(?)`; parameter count depends on columns, not rows. They do not use Trino's `EXECUTE IMMEDIATE` text-size splitting or commit-conflict retry loop; DuckDB resource/file-lock limits apply instead |
| Operations | No Iceberg snapshots, catalog, object storage, Kafka integration, scheduled detection worker, or lakehouse maintenance. Existing vendor findings still normalize into `application_logs` unchanged |

## Implementation and verification

`ulpf/services/backend.py` defines the structural `QueryBackend` contract using the existing method names. `TrinoService` only gains that contract and imports the shared error type; its SQL and ingestion implementation are unchanged. DuckDB code is separated into the backend, trusted DDL/query adaptations, and event-to-column mappings. `ulpf/ui/homelab.py` is the isolated app route. The config's Trino authentication import is lazy so local mode does not require that driver.

```bash
pip install pytest==8.4.2
HOMELAB_ISOLATED=1 pytest -q tests/test_duckdb_backend.py tests/test_duckdb_recovery.py tests/test_homelab_app.py tests/test_input_limits.py tests/test_parser_resource_safety.py
```

Use `HOMELAB_ISOLATED=1` only in the lightweight-only environment; it verifies the lakehouse packages are absent. The separate Homelab CI workflow tests both isolated dependencies and full-driver parity. The original CI workflow and existing tests remain unchanged. Tests cover empty dashboards, all shared analytical queries, OCSF/timestamp round-trips, quarantine, reopen/replay, rollback, concurrent sessions, row limits, query interruption, SQL safety and the actual app route with outbound connections blocked. The backend-to-Trino column-mapping comparison runs only where the Trino package is installed.

DuckDB references: [Python DB API and read-only connections](https://duckdb.org/docs/current/clients/python/dbapi), [security controls and their limits](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview), [pinned package and platform wheels](https://pypi.org/project/duckdb/1.5.5/).

### Development validation, September 10, 2026

Initial validation used bound multi-row inserts and passed a 2,500-event transaction. The subsequent stress audit replaced row-expanded placeholders with bound column lists: the same-machine 10,000-event comparison improved from 4.31 to 1.27 seconds for insertion and from 3.62 to 1.01 seconds for replay. These are single-run observations, not Raspberry Pi benchmarks or capacity promises. The [stress report](stress-testing.md) includes the failures as well as the successes.
