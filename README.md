# ULPF Lakehouse

ULPF ingests heterogeneous security logs, preserves the original evidence, normalizes records to an OCSF-inspired schema, and commits them to Apache Iceberg. Analysts can explore current data and run Trino SQL from a Streamlit web application.

## Architecture

```text
JSON / Syslog / CEF / Apache / Log4j
                 │
                 ▼
      Parser + OCSF normalizer
                 │ parameterized batches
                 ▼
            Apache Trino ───────▶ Iceberg REST Catalog
                 │                         │
                 └──── Parquet + metadata ▶ MinIO
```

- **MinIO** provides S3-compatible persistent object storage in the `minio-data` Docker volume.
- **Apache Iceberg REST fixture** is the catalog service for this local development stack.
- **Apache Trino** creates, writes, maintains, and queries the Iceberg table.
- **Streamlit** provides ingestion, current-state analytics, exports, stack health, and a SQL workspace.

The original single-file prototype is split by responsibility under `ulpf/`: parsers, normalization, pipeline, infrastructure services, SQL definitions, and UI components.

## Run the complete stack

Requirements: Docker Engine with the Compose plugin.

```bash
cp .env.example .env
docker compose up --build
```

Open:

- ULPF application: <http://localhost:8501>
- Trino console: <http://localhost:8080>
- MinIO console: <http://localhost:9001>
- Iceberg REST endpoint: <http://localhost:8181>

The app creates `iceberg.logging.application_logs` automatically. Choose Sample, Upload, or Paste in the left panel and select **Ingest into Iceberg**. MinIO objects survive container recreation because Compose uses a named volume.

To stop the services without deleting data:

```bash
docker compose down
```

Only `docker compose down --volumes` deletes the local MinIO warehouse.

## SQL workspace safety

The browser SQL workspace accepts one statement at a time, limits displayed results to 1,000 rows, and allows only read-oriented statements by default. This protects the shared Iceberg table from accidental DDL or DML.

For a trusted local environment, enable mutations in `.env`:

```dotenv
ULPF_ALLOW_MUTATING_SQL=true
```

In production, keep the console read-only, configure Trino authentication/TLS and catalog access control, use scoped MinIO credentials, and replace the development REST fixture with a production catalog such as Lakekeeper or Apache Polaris backed by a durable database.

## Maintenance

Compaction, snapshot expiration, and orphan cleanup statements are in `infra/maintenance.sql`. Schedule them after choosing retention rules appropriate to your audit requirements; snapshot expiration changes the available time-travel window.

## Local tests

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
ruff check .
```

The tests cover format detection, lossless preservation, SQL-console guards, and parameterized ingestion.
