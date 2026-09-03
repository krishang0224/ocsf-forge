"""Lakehouse schema and curated analytical queries."""

CREATE_SCHEMA = "CREATE SCHEMA IF NOT EXISTS iceberg.logging"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS iceberg.logging.application_logs (
    event_id VARCHAR,
    event_timestamp TIMESTAMP(6) WITH TIME ZONE,
    ingested_at TIMESTAMP(6) WITH TIME ZONE,
    service_name VARCHAR,
    log_level VARCHAR,
    message VARCHAR,
    user_id VARCHAR,
    ip_address VARCHAR,
    dst_ip_address VARCHAR,
    source_format VARCHAR,
    ocsf_version VARCHAR,
    category VARCHAR,
    category_uid INTEGER,
    class_name VARCHAR,
    class_uid INTEGER,
    severity_id INTEGER,
    action VARCHAR,
    disposition VARCHAR,
    status VARCHAR,
    hostname VARCHAR,
    device_vendor VARCHAR,
    raw_payload_hash VARCHAR,
    original_raw_payload VARCHAR,
    parse_success BOOLEAN,
    metadata_json VARCHAR
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['day(event_timestamp)', 'log_level']
)
""".strip()

OVERVIEW_QUERY = """
SELECT
    count(*) AS total_events,
    count_if(log_level IN ('High', 'Critical')) AS high_critical,
    count(DISTINCT NULLIF(ip_address, '')) AS unique_source_ips,
    round(100.0 * count_if(parse_success) / NULLIF(count(*), 0), 1) AS parse_rate
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
    "Iceberg snapshots": 'SELECT * FROM iceberg.logging."application_logs$snapshots" ORDER BY committed_at DESC',
}
