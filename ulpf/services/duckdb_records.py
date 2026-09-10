"""Map existing NormalizedEvent fields to the shared storage column names."""

import json
from datetime import UTC, datetime
from typing import Any

from ulpf.models import NormalizedEvent


def timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def raw_record(event: NormalizedEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id, "ingestion_run_id": event.ingestion_run_id, "source_id": event.source_id,
        "source_name": event.source_name, "source_type": event.source_format, "source_offset": event.source_offset,
        "observed_at": timestamp(event.observed_at), "raw_payload": event.original_raw_payload,
        "raw_payload_hash": event.raw_payload_hash, "parser_name": event.parser_name,
        "parser_version": event.parser_version,
        "detection_confidence": float((event.metadata or {}).get("detection_confidence", 0.0)),
        "parse_success": event.parse_success,
    }


def normalized_record(event: NormalizedEvent) -> dict[str, Any]:
    aliases = {
        "event_timestamp": "timestamp", "service_name": "device_product", "log_level": "severity",
        "user_id": "user", "ip_address": "src_endpoint_ip", "src_port": "src_endpoint_port",
        "dst_ip_address": "dst_endpoint_ip", "dst_port": "dst_endpoint_port",
    }
    names = (
        "event_id ingestion_run_id event_timestamp observed_at original_timestamp timezone_offset time_source "
        "service_name log_level message user_id ip_address src_port dst_ip_address dst_port source_format source_id "
        "source_name source_offset parser_name parser_version ocsf_version category category_uid class_name class_uid "
        "activity_name activity_id type_uid severity_id action disposition status status_id hostname device_vendor raw_payload_hash"
    ).split()
    record = {name: getattr(event, aliases.get(name, name)) for name in names}
    for name in ("event_timestamp", "observed_at"):
        record[name] = timestamp(record[name])
    record.update(
        ingested_at=datetime.now(UTC),
        metadata_json=json.dumps(event.metadata or {}, separators=(",", ":"), default=str),
        ocsf_json=json.dumps(event.to_ocsf_dict(), separators=(",", ":"), default=str),
    )
    return record


def quarantine_record(event: NormalizedEvent) -> dict[str, Any]:
    record = raw_record(event)
    del record["parse_success"], record["detection_confidence"]
    record.update(
        original_timestamp=event.original_timestamp, error_code="PARSE_OR_VALIDATION_ERROR", error_message=event.parse_notes,
        metadata_json=json.dumps(event.metadata or {}, separators=(",", ":"), default=str),
    )
    return record
