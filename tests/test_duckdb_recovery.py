import importlib.util
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from ulpf.config import settings
from ulpf.pipeline import run_pipeline
from ulpf.sample_data import SAMPLE_LOGS

pytestmark = pytest.mark.skipif(importlib.util.find_spec("duckdb") is None, reason="requires requirements-homelab.txt")
ROOT = Path(__file__).resolve().parents[1]


def test_engine_memory_exhaustion_rolls_back_and_recovers(tmp_path, monkeypatch):
    import duckdb

    from ulpf.services.duckdb_backend import DuckDBBackend

    backend = DuckDBBackend(replace(settings, backend="duckdb", homelab_directory=str(tmp_path), duckdb_memory_limit="64MB"))
    backend.ensure_lakehouse()
    original = backend._insert_records

    def exhaust(connection, table, records):
        if table == "application_logs":
            connection.execute("SELECT list(i) FROM range(10000000) t(i)")
        return original(connection, table, records)

    with monkeypatch.context() as patch:
        patch.setattr(backend, "_insert_records", exhaust)
        with pytest.raises(duckdb.OutOfMemoryException):
            backend.ingest_events(run_pipeline(SAMPLE_LOGS))
    for table in ("raw_events", "application_logs", "quarantine_events"):
        assert backend.execute(f"SELECT count(*) FROM {table}")[1] == [[0]]
    assert backend.execute("SELECT status FROM ingestion_runs")[1] == [["FAILED"]]
    assert backend.ingest_events(run_pipeline(SAMPLE_LOGS)).committed == 8


def test_process_crash_does_not_commit_partial_events(tmp_path):
    from ulpf.services.duckdb_backend import DuckDBBackend

    backend = DuckDBBackend(replace(settings, backend="duckdb", homelab_directory=str(tmp_path)))
    backend.ensure_lakehouse()
    assert backend.insert_events(run_pipeline(['{"message":"already committed"}'], source_id="before")) == 1
    script = """
import os
from ulpf.services.duckdb_backend import DuckDBBackend
from ulpf.pipeline import run_pipeline
from ulpf.sample_data import SAMPLE_LOGS
backend = DuckDBBackend()
original = backend._insert_records
def crash(connection, table, records):
    if table == 'application_logs':
        os._exit(77)
    return original(connection, table, records)
backend._insert_records = crash
backend.ingest_events(run_pipeline(SAMPLE_LOGS, source_id='crash'))
"""
    env = {**os.environ, "ULPF_BACKEND": "duckdb", "ULPF_HOMELAB_DIRECTORY": str(tmp_path)}
    child = subprocess.run([sys.executable, "-c", script], env=env, cwd=ROOT, capture_output=True, timeout=30)
    assert child.returncode == 77, child.stderr.decode()
    for table in ("raw_events", "application_logs"):
        assert backend.execute(f"SELECT source_id FROM {table}")[1] == [["before"]]
    assert backend.execute("SELECT count(*) FROM ingestion_runs")[1] == [[1]]
    events = run_pipeline(SAMPLE_LOGS, source_id="crash")
    assert backend.ingest_events(events).committed == 8
    assert backend.ingest_events(events).duplicates == 8
