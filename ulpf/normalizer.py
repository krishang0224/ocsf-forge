"""Map parsed records to a stable OCSF-inspired taxonomy."""

import hashlib
import uuid
from datetime import UTC, datetime

from ulpf.models import SEVERITY_IDS, NormalizedEvent


class OCSFNormalizer:
    CATEGORY_BY_FORMAT = {
        "syslog": ("Network Activity", 4),
        "apache": ("Network Activity", 4),
        "cef": ("Findings", 2),
        "json": ("Audit Activity", 3),
        "log4j": ("Application Activity", 6),
    }
    CLASS_BY_ACTION = {
        "Denied": ("Firewall Activity", 2003),
        "Blocked": ("Firewall Activity", 2003),
        "Allowed": ("Firewall Activity", 2003),
        "Detected": ("Detection Finding", 2004),
        "Login Failure": ("Authentication", 3002),
    }

    def normalize(self, raw_line: str, fmt: str, parsed: dict) -> NormalizedEvent:
        category, category_uid = self.CATEGORY_BY_FORMAT.get(fmt, ("Uncategorized", 99))
        class_name, class_uid = self.CLASS_BY_ACTION.get(parsed.get("action", ""), ("Base Event", 0))
        severity = parsed.get("severity", "Informational")
        timestamp = parsed.get("timestamp") or datetime.now(UTC).isoformat()
        return NormalizedEvent(
            event_id=str(uuid.uuid4()),
            timestamp=timestamp,
            category=category,
            category_uid=category_uid,
            class_name=class_name,
            class_uid=class_uid,
            severity=severity,
            severity_id=SEVERITY_IDS.get(severity, 1),
            status=parsed.get("status", "Success" if parsed.get("_parsed") else "Failure"),
            disposition=parsed.get("disposition", "Unknown"),
            action=parsed.get("action", "Unknown"),
            src_endpoint_ip=parsed.get("src_endpoint_ip", "") or "",
            src_endpoint_port=parsed.get("src_endpoint_port"),
            dst_endpoint_ip=parsed.get("dst_endpoint_ip", "") or "",
            dst_endpoint_port=parsed.get("dst_endpoint_port"),
            user=parsed.get("user", "") or "",
            hostname=parsed.get("hostname", "") or "",
            device_vendor=parsed.get("device_vendor", "") or "",
            device_product=parsed.get("device_product", fmt) or fmt,
            message=str(parsed.get("message", ""))[:2000],
            raw_payload_hash=hashlib.sha256(raw_line.encode("utf-8", errors="replace")).hexdigest(),
            original_raw_payload=raw_line.rstrip("\n"),
            source_format=fmt,
            parse_success=bool(parsed.get("_parsed")),
            parse_notes="" if parsed.get("_parsed") else "Format not recognized or extraction incomplete",
            metadata=parsed.get("metadata", {}),
        )
