"""CEF and LEEF security-product parsers."""

import re
from datetime import datetime

from ulpf.parsing.base import split_escaped, unescape_cef

EXTENSION_KEY = re.compile(r"(?<!\\)(?:^|\s)([A-Za-z0-9_.-]+)=")


def parse_extensions(value: str) -> dict[str, str]:
    matches = list(EXTENSION_KEY.finditer(value))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        result[match.group(1)] = unescape_cef(value[match.end() : end].strip())
    return result


class CefParser:
    name = "cef"
    source_format = "cef"
    version = "2.0.0"

    def detect(self, value: str) -> float:
        return 1.0 if value.lstrip().startswith("CEF:") else 0.0

    def parse(self, value: str, observed_at: datetime) -> dict:
        parts = split_escaped(value.strip()[4:], "|", maxsplit=7)
        if len(parts) != 8 or not parts[0].isdigit():
            return {"_parsed": False, "parse_notes": "Malformed CEF header"}
        version, vendor, product, device_version, signature_id, name, raw_severity, extension = parts
        ext = parse_extensions(extension)
        try:
            level = int(raw_severity)
            severity = "Critical" if level >= 9 else "High" if level >= 7 else "Medium" if level >= 4 else "Low"
        except ValueError:
            severity = raw_severity.title() or "Unknown"
        timestamp = ext.get("rt") or ext.get("start") or ext.get("end") or ""
        return {
            "_parsed": True,
            "timestamp": timestamp,
            "timestamp_missing_ok": not timestamp,
            "hostname": ext.get("dhost", ext.get("dvchost", "")),
            "device_vendor": unescape_cef(vendor),
            "device_product": unescape_cef(product),
            "message": ext.get("msg") or unescape_cef(name),
            "severity": severity,
            "status": "New",
            "action": ext.get("act", "Detected"),
            "disposition": ext.get("outcome", "Unknown"),
            "src_endpoint_ip": ext.get("src", ""),
            "dst_endpoint_ip": ext.get("dst", ""),
            "src_endpoint_port": ext.get("spt"),
            "dst_endpoint_port": ext.get("dpt"),
            "user": ext.get("suser", ext.get("duser", "")),
            "metadata": {**ext, "cef_version": version, "device_version": device_version, "signature_id": signature_id},
            "ocsf_class": "Detection Finding",
            "class_uid": 2004,
            "category": "Findings",
            "category_uid": 2,
            "activity_id": 1,
            "activity_name": "Create",
        }


class LeefParser:
    name = "leef"
    source_format = "leef"
    version = "1.1.0"

    def detect(self, value: str) -> float:
        return 1.0 if value.lstrip().startswith("LEEF:") else 0.0

    def parse(self, value: str, observed_at: datetime) -> dict:
        parts = split_escaped(value.strip()[5:], "|", maxsplit=5)
        if len(parts) < 5:
            return {"_parsed": False, "parse_notes": "Malformed LEEF header"}
        version, vendor, product, device_version, event_id, *remaining = parts
        payload = remaining[0] if remaining else ""
        separator = "\t"
        if version.startswith("2") and payload:
            separator, _, payload = payload.partition("|")
            separator = {"0x09": "\t", "^": "^"}.get(separator, separator or "\t")
        ext: dict[str, str] = {}
        for field in split_escaped(payload, separator):
            key, marker, field_value = field.partition("=")
            if marker:
                ext[key.strip()] = unescape_cef(field_value.strip())
        severity_value = ext.get("sev", ext.get("severity", "Informational"))
        try:
            numeric = int(severity_value)
            severity = "Critical" if numeric >= 9 else "High" if numeric >= 7 else "Medium" if numeric >= 4 else "Low"
        except ValueError:
            severity = severity_value.title()
        timestamp = ext.get("devTime") or ""
        return {
            "_parsed": True,
            "timestamp": timestamp,
            "timestamp_missing_ok": not timestamp,
            "hostname": ext.get("devName", ""),
            "device_vendor": vendor,
            "device_product": product,
            "message": ext.get("msg", event_id),
            "severity": severity,
            "status": "New",
            "action": ext.get("cat", "Detected"),
            "src_endpoint_ip": ext.get("src", ""),
            "dst_endpoint_ip": ext.get("dst", ""),
            "user": ext.get("usrName", ""),
            "metadata": {**ext, "leef_version": version, "device_version": device_version, "event_id": event_id},
            "ocsf_class": "Detection Finding",
            "class_uid": 2004,
            "category": "Findings",
            "category_uid": 2,
            "activity_id": 1,
            "activity_name": "Create",
        }
