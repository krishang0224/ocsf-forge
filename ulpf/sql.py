"""Lakehouse schemas, migrations, and curated analytical queries."""

CREATE_SCHEMA = "CREATE SCHEMA IF NOT EXISTS iceberg.logging"

CREATE_RAW_TABLE = """
CREATE TABLE IF NOT EXISTS iceberg.logging.raw_events (
    event_id VARCHAR,
    ingestion_run_id VARCHAR,
    source_id VARCHAR,
    source_name VARCHAR,
    source_type VARCHAR,
    source_offset BIGINT,
    observed_at TIMESTAMP(6) WITH TIME ZONE,
    raw_payload VARCHAR,
    raw_payload_hash VARCHAR,
    parser_name VARCHAR,
    parser_version VARCHAR,
    detection_confidence DOUBLE,
    parse_success BOOLEAN
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['day(observed_at)', 'source_type']
)
""".strip()

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS iceberg.logging.application_logs (
    event_id VARCHAR,
    ingestion_run_id VARCHAR,
    event_timestamp TIMESTAMP(6) WITH TIME ZONE,
    observed_at TIMESTAMP(6) WITH TIME ZONE,
    ingested_at TIMESTAMP(6) WITH TIME ZONE,
    original_timestamp VARCHAR,
    timezone_offset INTEGER,
    time_source VARCHAR,
    service_name VARCHAR,
    log_level VARCHAR,
    message VARCHAR,
    user_id VARCHAR,
    ip_address VARCHAR,
    src_port INTEGER,
    dst_ip_address VARCHAR,
    dst_port INTEGER,
    source_format VARCHAR,
    source_id VARCHAR,
    source_name VARCHAR,
    source_offset BIGINT,
    parser_name VARCHAR,
    parser_version VARCHAR,
    ocsf_version VARCHAR,
    category VARCHAR,
    category_uid INTEGER,
    class_name VARCHAR,
    class_uid INTEGER,
    activity_name VARCHAR,
    activity_id INTEGER,
    type_uid BIGINT,
    severity_id INTEGER,
    action VARCHAR,
    disposition VARCHAR,
    status VARCHAR,
    status_id INTEGER,
    hostname VARCHAR,
    device_vendor VARCHAR,
    raw_payload_hash VARCHAR,
    metadata_json VARCHAR,
    ocsf_json VARCHAR
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['day(event_timestamp)', 'log_level']
)
""".strip()

CREATE_QUARANTINE_TABLE = """
CREATE TABLE IF NOT EXISTS iceberg.logging.quarantine_events (
    event_id VARCHAR,
    ingestion_run_id VARCHAR,
    source_id VARCHAR,
    source_name VARCHAR,
    source_type VARCHAR,
    source_offset BIGINT,
    observed_at TIMESTAMP(6) WITH TIME ZONE,
    original_timestamp VARCHAR,
    parser_name VARCHAR,
    parser_version VARCHAR,
    error_code VARCHAR,
    error_message VARCHAR,
    raw_payload VARCHAR,
    raw_payload_hash VARCHAR,
    metadata_json VARCHAR
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['day(observed_at)', 'source_type']
)
""".strip()

CREATE_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS iceberg.logging.ingestion_runs (
    run_id VARCHAR,
    source_id VARCHAR,
    source_name VARCHAR,
    source_type VARCHAR,
    started_at TIMESTAMP(6) WITH TIME ZONE,
    completed_at TIMESTAMP(6) WITH TIME ZONE,
    status VARCHAR,
    received_count BIGINT,
    parsed_count BIGINT,
    quarantined_count BIGINT,
    committed_count BIGINT,
    duplicate_count BIGINT,
    snapshot_id BIGINT,
    error_message VARCHAR
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['day(started_at)']
)
""".strip()

APPLICATION_LOG_MIGRATIONS = [
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS ingestion_run_id VARCHAR",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS observed_at TIMESTAMP(6) WITH TIME ZONE",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS original_timestamp VARCHAR",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS timezone_offset INTEGER",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS time_source VARCHAR",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS src_port INTEGER",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS dst_port INTEGER",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS source_id VARCHAR",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS source_name VARCHAR",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS source_offset BIGINT",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS parser_name VARCHAR",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS parser_version VARCHAR",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS activity_name VARCHAR",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS activity_id INTEGER",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS type_uid BIGINT",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS status_id INTEGER",
    "ALTER TABLE iceberg.logging.application_logs ADD COLUMN IF NOT EXISTS ocsf_json VARCHAR",
]

LAKEHOUSE_SETUP = [
    CREATE_SCHEMA,
    CREATE_RAW_TABLE,
    CREATE_TABLE,
    CREATE_QUARANTINE_TABLE,
    CREATE_RUNS_TABLE,
    *APPLICATION_LOG_MIGRATIONS,
]

OVERVIEW_QUERY = """
SELECT
    count(*) AS total_events,
    count_if(log_level IN ('High', 'Critical')) AS high_critical,
    count(DISTINCT NULLIF(ip_address, '')) AS unique_source_ips,
    (SELECT coalesce(round(100.0 * count_if(parse_success) / NULLIF(count(*), 0), 1), 0.0)
       FROM iceberg.logging.raw_events) AS parse_rate
FROM iceberg.logging.application_logs
""".strip()

RECENT_QUERY = """
SELECT event_timestamp, log_level, service_name, source_format, ip_address,
       user_id, action, message, event_id
FROM iceberg.logging.application_logs
ORDER BY event_timestamp DESC
LIMIT 500
""".strip()

SEVERITY_QUERY = """
SELECT log_level, count(*) AS events
FROM iceberg.logging.application_logs
GROUP BY log_level
ORDER BY events DESC
""".strip()

SERVICE_QUERY = """
SELECT service_name, count(*) AS events,
       count_if(log_level IN ('High', 'Critical')) AS threats
FROM iceberg.logging.application_logs
GROUP BY service_name
ORDER BY events DESC
LIMIT 12
""".strip()

QUALITY_QUERY = """
SELECT parser_name, source_type,
       count(*) AS received,
       count_if(parse_success) AS parsed,
       round(100.0 * count_if(parse_success) / NULLIF(count(*), 0), 1) AS success_rate
FROM iceberg.logging.raw_events
GROUP BY parser_name, source_type
ORDER BY received DESC
""".strip()

RUNS_QUERY = """
SELECT started_at, source_name, source_type, status, received_count,
       committed_count, quarantined_count, duplicate_count, run_id
FROM iceberg.logging.ingestion_runs
ORDER BY started_at DESC
LIMIT 100
""".strip()

WAREHOUSE_QUERY = """
SELECT
    (SELECT count(*) FROM iceberg.logging."application_logs$files") AS data_files,
    (SELECT coalesce(round(avg(file_size_in_bytes) / 1048576.0, 2), 0.0)
       FROM iceberg.logging."application_logs$files") AS average_file_mb,
    (SELECT count(*) FROM iceberg.logging."application_logs$snapshots") AS snapshots
""".strip()

EXAMPLE_QUERIES = {
    "Latest high-severity events": """SELECT event_timestamp, service_name, log_level, ip_address, message
FROM iceberg.logging.application_logs
WHERE log_level IN ('High', 'Critical')
ORDER BY event_timestamp DESC
LIMIT 100""",
    "Errors by service (24h)": """SELECT service_name, count(*) AS total_errors, arbitrary(message) AS sample_message
FROM iceberg.logging.application_logs
WHERE event_timestamp >= current_timestamp - INTERVAL '24' HOUR
  AND log_level IN ('High', 'Critical')
GROUP BY service_name
ORDER BY total_errors DESC""",
    "Quarantined records": """SELECT observed_at, source_name, source_type, error_code, error_message
FROM iceberg.logging.quarantine_events
ORDER BY observed_at DESC
LIMIT 100""",
    "Iceberg snapshots": 'SELECT * FROM iceberg.logging."application_logs$snapshots" ORDER BY committed_at DESC',
}
