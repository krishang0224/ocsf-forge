import json
import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ulpf.config import settings
from ulpf.detection.config import DetectionSettings
from ulpf.detection.demo import demo_logs
from ulpf.detection.store import DetectionStore
from ulpf.detection.worker import run_once
from ulpf.pipeline import run_pipeline
from ulpf.services.trino import TrinoService


@pytest.mark.skipif(os.getenv("ULPF_RUN_LIVE_TESTS") != "1", reason="requires a local Trino/MinIO stack")
def test_live_findings_replay_evidence_and_permissions():
    config = replace(settings, trino_host="localhost", trino_user="ulpf_writer", trino_request_timeout=30)
    writer = TrinoService(config)
    detector = DetectionStore(replace(config, trino_user="ulpf_detector"))
    reader = TrinoService(replace(config, trino_user="ulpf_reader"))
    writer.ensure_lakehouse()
    detector.ensure_storage()
    source = f"detection-test-{uuid.uuid4().hex}"
    host = f"{source}.example"
    end = datetime.now(UTC)
    events = run_pipeline(demo_logs(end, hostname=host), source_id=source)
    try:
        result = writer.ingest_events(events)
        assert result.committed == 15 and result.quarantined == 0
        for _ in range(2):
            run_once(detector, DetectionSettings(), start=end - timedelta(minutes=10), end=end)
        _, rows = reader.execute(
            "SELECT event_id, rule_id, class_uid, ocsf_json FROM iceberg.logging.detections WHERE hostname = ?",
            [host],
        )
        assert len(rows) == len({row[0] for row in rows}) == 3
        assert {row[1] for row in rows} == {
            "auth.repeated_failures", "auth.password_spray", "auth.success_after_failures",
        }
        ids = {event.event_id for event in events}
        for finding_id, _, class_uid, payload in rows:
            record = json.loads(payload)
            assert class_uid == record["class_uid"] == 2004
            assert record["finding_info"]["uid"] == finding_id
            assert set(record["unmapped"]["evidence_event_ids"]) <= ids
        with pytest.raises(Exception, match="Access Denied"):
            detector.execute("SELECT event_id FROM iceberg.logging.raw_events LIMIT 1")
        with pytest.raises(Exception, match="Access Denied"):
            detector.execute("DELETE FROM iceberg.logging.application_logs WHERE false")
        with pytest.raises(Exception, match="Access Denied"):
            reader.execute("DELETE FROM iceberg.logging.detections WHERE false")
    finally:
        writer.execute("DELETE FROM iceberg.logging.detections WHERE hostname = ?", [host])
        for table in ("application_logs", "raw_events", "quarantine_events", "ingestion_runs"):
            writer.execute(f"DELETE FROM iceberg.logging.{table} WHERE source_id = ?", [source])
