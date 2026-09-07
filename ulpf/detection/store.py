"""Bounded reads and idempotent finding writes through Trino."""

import json
from datetime import datetime

from ulpf.detection.models import AuthenticationEvent, Detection
from ulpf.detection.sql import CREATE_DETECTIONS_TABLE
from ulpf.services.trino import TrinoService
from ulpf.sql import CREATE_SCHEMA

DETECTION_COLUMNS = (
    "event_id", "detected_at", "rule_id", "rule_version", "title", "severity_id", "status",
    "class_uid", "category_uid", "activity_id", "type_uid", "first_seen", "last_seen", "hostname",
    "service_name", "ip_address", "user_id", "event_count", "evidence_event_ids_json", "ocsf_json",
)


class DetectionStore(TrinoService):
    def ensure_storage(self) -> None:
        with self._connection() as connection:
            self._execute_on_connection(connection, CREATE_SCHEMA)
            self._execute_on_connection(connection, CREATE_DETECTIONS_TABLE)

    def read_authentication(self, start: datetime, end: datetime, max_events: int) -> list[AuthenticationEvent]:
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        _, rows = self.execute(
            "SELECT event_id, event_timestamp, hostname, service_name, ip_address, user_id, status_id "
            "FROM iceberg.logging.application_logs "
            "WHERE class_uid = 3002 AND activity_id = 1 AND status_id IN (1, 2) "
            "AND event_timestamp >= ? AND event_timestamp < ? "
            f"ORDER BY event_timestamp, event_id LIMIT {max_events + 1}",
            [start, end], row_limit=max_events + 1,
        )
        if len(rows) > max_events:
            raise ValueError("Detection scan exceeds max_events; reduce the range or raise the limit. No findings written.")
        return [AuthenticationEvent(*row) for row in rows]

    def write_findings(self, findings: list[Detection]) -> None:
        unique = list({finding.event_id: finding for finding in findings}.values())
        if not unique:
            return
        self._assert_events_fit("iceberg.logging.detections", DETECTION_COLUMNS, unique, self._values)
        with self._connection() as connection:
            self._merge_batches(connection, "iceberg.logging.detections", DETECTION_COLUMNS, unique, self._values)

    @staticmethod
    def _values(finding: Detection) -> tuple:
        event = finding.event
        return (
            finding.event_id, datetime.fromisoformat(event.observed_at), finding.rule_id, finding.rule_version,
            event.message, event.severity_id, event.status, event.class_uid, event.category_uid,
            event.activity_id, event.type_uid, finding.first_seen, finding.last_seen, event.hostname,
            event.metadata["service"], event.src_endpoint_ip, event.user, finding.event_count,
            json.dumps(finding.evidence_ids, separators=(",", ":")),
            json.dumps(finding.to_ocsf_dict(), separators=(",", ":")),
        )
