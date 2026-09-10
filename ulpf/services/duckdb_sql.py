"""DuckDB-only schema adaptation; shared analytical SQL remains unchanged."""

import re

from ulpf.sql import (
    CREATE_QUARANTINE_TABLE,
    CREATE_RAW_TABLE,
    CREATE_RUNS_TABLE,
    CREATE_TABLE,
    EXAMPLE_QUERIES,
    OVERVIEW_QUERY,
)


def native_ddl(statement: str) -> str:
    """Adapt only trusted, repository-owned DDL, never user SQL."""
    definition = statement.split("\nWITH (", 1)[0]
    definition = definition.replace("TIMESTAMP(6) WITH TIME ZONE", "TIMESTAMPTZ")
    key = "run_id" if "ingestion_runs" in definition else "event_id"
    return re.sub(rf"\b{key} VARCHAR\b", f"{key} VARCHAR PRIMARY KEY", definition, count=1)


SETUP = [
    "CREATE SCHEMA IF NOT EXISTS iceberg.logging",
    *(native_ddl(statement) for statement in (CREATE_RAW_TABLE, CREATE_TABLE, CREATE_QUARANTINE_TABLE, CREATE_RUNS_TABLE)),
]

READ_ADAPTATIONS = {
    OVERVIEW_QUERY: OVERVIEW_QUERY.replace(
        "count_if(log_level IN ('High', 'Critical')) AS high_critical",
        "coalesce(count_if(log_level IN ('High', 'Critical')), 0) AS high_critical",
    ),
}

EXAMPLES = {name: sql for name, sql in EXAMPLE_QUERIES.items()
            if name not in {"Iceberg snapshots", "Local detection findings"}}
EXAMPLES["Local tables"] = "SELECT table_name, estimated_size FROM duckdb_tables() WHERE schema_name = 'logging'"
