"""Normalized OCSF-inspired event model."""

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class NormalizedEvent:
    ocsf_version: str = "1.1.0"
    event_id: str = ""
    timestamp: str = ""
    category_uid: int = 0
    class_uid: int = 0
    category: str = "Uncategorized"
    class_name: str = "Base Event"
    severity: str = "Informational"
    severity_id: int = 1
    status: str = "Unknown"
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
    parse_success: bool = True
    parse_notes: str = ""
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


SEVERITY_IDS = {
    "Unknown": 0,
    "Informational": 1,
    "Low": 2,
    "Medium": 3,
    "High": 4,
    "Critical": 6,
}
