"""Map parsed records to validated OCSF 1.8 classification fields."""

import hashlib
import ipaddress
from datetime import UTC, datetime

from ulpf.models import SEVERITY_IDS, STATUS_IDS, NormalizedEvent

OCSF_CLASS_CATEGORIES = {2004: 2, 3002: 3, 4001: 4, 4002: 4, 6003: 6, 6008: 6}


class OCSFNormalizer:
    def normalize(
        self,
        raw_line: str,
        fmt: str,
        parsed: dict,
        *,
        observed_at: datetime | None = None,
        source_id: str = "interactive",
        source_offset: int = 0,
        source_name: str = "",
        ingestion_run_id: str = "",
    ) -> NormalizedEvent:
        observed = observed_at or datetime.now(UTC)
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        category = parsed.get("category", "Other")
        category_uid = int(parsed.get("category_uid", 0))
        class_name = parsed.get("ocsf_class", "Base Event")
        class_uid = int(parsed.get("class_uid", 0))
        activity_id = int(parsed.get("activity_id", 0))
        activity_name = parsed.get("activity_name", "Unknown")
        severity = parsed.get("severity", "Informational")
        original_timestamp = str(parsed.get("timestamp") or "")
        timestamp, timestamp_error, timezone_offset, time_source = self._timestamp(
            original_timestamp, observed, bool(parsed.get("timestamp_missing_ok"))
        )
        src_ip, src_ip_error = self._ip(parsed.get("src_endpoint_ip"), "source")
        dst_ip, dst_ip_error = self._ip(parsed.get("dst_endpoint_ip"), "destination")
        src_port, src_port_error = self._port(parsed.get("src_endpoint_port"), "source")
        dst_port, dst_port_error = self._port(parsed.get("dst_endpoint_port"), "destination")
        validation_errors = [
            error for error in (timestamp_error, src_ip_error, dst_ip_error, src_port_error, dst_port_error) if error
        ]
        if parsed.get("_parsed"):
            expected_category = OCSF_CLASS_CATEGORIES.get(class_uid)
            if expected_category is None:
                validation_errors.append(f"Unsupported OCSF class UID: {class_uid}")
            elif category_uid != expected_category:
                validation_errors.append(
                    f"OCSF class {class_uid} belongs to category {expected_category}, not {category_uid}"
                )
        if severity not in SEVERITY_IDS:
            validation_errors.append(f"Unknown OCSF severity: {severity}")
        parse_success = bool(parsed.get("_parsed")) and not validation_errors and class_uid > 0 and activity_id > 0
        notes = parsed.get("parse_notes", "")
        if validation_errors:
            notes = "; ".join(filter(None, (notes, *validation_errors)))
        if parsed.get("_parsed") and (class_uid <= 0 or activity_id <= 0):
            notes = "; ".join(filter(None, (notes, "OCSF classification is incomplete")))
        default_status = "New" if class_uid == 2004 else "Success" if parse_success else "Failure"
        status = str(parsed.get("status", default_status)).title()
        status_ids = (
            {"Unknown": 0, "New": 1, "In Progress": 2, "Suppressed": 3, "Resolved": 4, "Archived": 5, "Deleted": 6}
            if class_uid == 2004
            else STATUS_IDS
        )
        raw_hash = hashlib.sha256(raw_line.encode("utf-8", errors="replace")).hexdigest()
        event_id = hashlib.sha256(f"{source_id}\0{source_offset}\0{raw_hash}".encode()).hexdigest()
        return NormalizedEvent(
            event_id=event_id,
            timestamp=timestamp,
            original_timestamp=original_timestamp,
            observed_at=observed.isoformat(),
            timezone_offset=timezone_offset,
            time_source=time_source,
            category=category,
            category_uid=category_uid,
            class_name=class_name,
            class_uid=class_uid,
            activity_id=activity_id,
            activity_name=activity_name,
            type_uid=class_uid * 100 + activity_id if class_uid and activity_id else 0,
            severity=severity,
            severity_id=SEVERITY_IDS.get(severity, 0),
            status=status,
            status_id=status_ids.get(status, 99 if status not in {"", "Unknown"} else 0),
            disposition=parsed.get("disposition", "Unknown"),
            action=parsed.get("action", "Unknown"),
            src_endpoint_ip=src_ip,
            src_endpoint_port=src_port,
            dst_endpoint_ip=dst_ip,
            dst_endpoint_port=dst_port,
            user=parsed.get("user", "") or "",
            hostname=parsed.get("hostname", "") or "",
            device_vendor=parsed.get("device_vendor", "") or "",
            device_product=parsed.get("device_product", fmt) or fmt,
            message=str(parsed.get("message", ""))[:2000],
            raw_payload_hash=raw_hash,
            original_raw_payload=raw_line.rstrip("\n"),
            source_format=fmt,
            source_id=source_id,
            source_offset=source_offset,
            source_name=source_name,
            ingestion_run_id=ingestion_run_id,
            parser_name=parsed.get("_parser_name", fmt),
            parser_version=parsed.get("_parser_version", "1.0.0"),
            parse_success=parse_success,
            parse_notes=notes or ("" if parse_success else "Format not recognized or extraction incomplete"),
            metadata={**parsed.get("metadata", {}), "detection_confidence": parsed.get("_detection_confidence", 1.0)},
        )

    @staticmethod
    def _port(value, label: str) -> tuple[int | None, str]:
        if value in (None, ""):
            return None, ""
        try:
            port = int(value)
        except (TypeError, ValueError):
            return None, f"Invalid {label} port: {value}"
        return (port, "") if 0 <= port <= 65535 else (None, f"Invalid {label} port: {value}")

    @staticmethod
    def _ip(value, label: str) -> tuple[str, str]:
        if value in (None, ""):
            return "", ""
        try:
            return str(ipaddress.ip_address(str(value))), ""
        except ValueError:
            return "", f"Invalid {label} IP address: {value}"

    @staticmethod
    def _timestamp(value: str, observed: datetime, missing_ok: bool) -> tuple[str | None, str, int | None, str]:
        if not value:
            if missing_ok:
                offset = observed.utcoffset()
                return observed.isoformat(), "", int(offset.total_seconds() / 60) if offset else 0, "collector"
            return None, "Missing source timestamp", None, "source"
        try:
            if value.isdigit():
                numeric = int(value)
                parsed = datetime.fromtimestamp(numeric / 1000 if numeric > 10_000_000_000 else numeric, UTC)
            else:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None, "Source timestamp has no timezone", None, "source"
            offset = parsed.utcoffset()
            return parsed.isoformat(), "", int(offset.total_seconds() / 60) if offset else 0, "source"
        except (OverflowError, OSError, ValueError):
            return None, f"Invalid source timestamp: {value}", None, "source"
