"""Domain models shared by parsing, normalization, storage, and the UI."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class NormalizedEvent:
    ocsf_version: str = "1.8.0"
    event_id: str = ""
    timestamp: str | None = None
    original_timestamp: str = ""
    observed_at: str = ""
    timezone_offset: int | None = None
    time_source: str = "source"
    category_uid: int = 0
    class_uid: int = 0
    activity_id: int = 0
    type_uid: int = 0
    category: str = "Other"
    class_name: str = "Base Event"
    activity_name: str = "Unknown"
    severity: str = "Informational"
    severity_id: int = 1
    status: str = "Unknown"
    status_id: int = 0
    disposition: str = "Unknown"
    action: str = "Unknown"
    src_endpoint_ip: str = ""
    src_endpoint_port: int | None = None
    dst_endpoint_ip: str = ""
    dst_endpoint_port: int | None = None
    user: str = ""
    hostname: str = ""
    device_vendor: str = ""
    device_product: str = ""
    message: str = ""
    raw_payload_hash: str = ""
    original_raw_payload: str = ""
    source_format: str = ""
    source_id: str = "interactive"
    source_offset: int = 0
    source_name: str = ""
    ingestion_run_id: str = ""
    parser_name: str = ""
    parser_version: str = ""
    parse_success: bool = True
    parse_notes: str = ""
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_ocsf_dict(self) -> dict[str, Any]:
        """Return a canonical OCSF event shape for interchange."""
        event_time = datetime.fromisoformat((self.timestamp or self.observed_at).replace("Z", "+00:00"))
        logged_time = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        record: dict[str, Any] = {
            "activity_id": self.activity_id,
            "activity_name": self.activity_name,
            "category_uid": self.category_uid,
            "category_name": self.category,
            "class_uid": self.class_uid,
            "class_name": self.class_name,
            "type_uid": self.type_uid,
            "type_name": f"{self.class_name}: {self.activity_name}",
            "severity_id": self.severity_id,
            "severity": self.severity,
            "status_id": self.status_id,
            "status": self.status,
            "time": int(event_time.timestamp() * 1000),
            "timezone_offset": self.timezone_offset,
            "message": self.message,
            "metadata": {
                "version": self.ocsf_version,
                "logged_time": int(logged_time.timestamp() * 1000),
                "product": {
                    "name": self.device_product or self.parser_name,
                    "vendor_name": self.device_vendor or "Unknown",
                    "version": self.parser_version,
                },
            },
            "unmapped": self.metadata or {},
        }
        if self.src_endpoint_ip or self.src_endpoint_port is not None:
            record["src_endpoint"] = {
                key: value
                for key, value in {"ip": self.src_endpoint_ip, "port": self.src_endpoint_port}.items()
                if value not in (None, "")
            }
        if self.dst_endpoint_ip or self.dst_endpoint_port is not None:
            record["dst_endpoint"] = {
                key: value
                for key, value in {"ip": self.dst_endpoint_ip, "port": self.dst_endpoint_port}.items()
                if value not in (None, "")
            }
        if self.user:
            record["actor"] = {"user": {"name": self.user}}
        if self.class_uid == 2004:
            record["finding_info"] = {
                "title": self.message or self.action,
                "uid": str((self.metadata or {}).get("signature_id") or self.event_id),
            }
            record["is_alert"] = True
        elif self.class_uid == 6003:
            record.setdefault("actor", {"user": {"name": "unknown"}})
            record["api"] = {"operation": self.action or self.activity_name}
        return record

    def to_json(self) -> str:
        return json.dumps(self.to_ocsf_dict(), indent=2, default=str)


@dataclass(frozen=True)
class IngestionRun:
    run_id: str
    source_id: str
    source_type: str
    source_name: str
    started_at: datetime
    total_records: int


@dataclass(frozen=True)
class IngestionResult:
    run_id: str
    received: int
    committed: int
    quarantined: int
    duplicates: int
    status: str


SEVERITY_IDS = {
    "Unknown": 0,
    "Informational": 1,
    "Low": 2,
    "Medium": 3,
    "High": 4,
    "Critical": 5,
    "Fatal": 6,
}

STATUS_IDS = {"Unknown": 0, "Success": 1, "Failure": 2}
