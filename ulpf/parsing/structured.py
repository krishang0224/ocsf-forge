"""Generic JSON, CSV-row, and XML-event parsers."""

import json
from datetime import datetime
from ipaddress import ip_address

from ulpf.parsing.authentication import authentication_action
from ulpf.parsing.json_document import decode_json

MAPPED_FIELDS = {
    "@timestamp",
    "action",
    "actor",
    "app",
    "client_ip",
    "client_port",
    "destination_ip",
    "destination_port",
    "dst_ip",
    "dst_port",
    "event",
    "event_type",
    "host",
    "hostname",
    "ip",
    "level",
    "message",
    "operation",
    "risk",
    "server",
    "server_port",
    "service",
    "severity",
    "source",
    "source_ip",
    "source_port",
    "src_ip",
    "src_port",
    "time",
    "timestamp",
    "user",
    "username",
    "vendor",
}


def structured_record(item: dict, observed_at: datetime) -> dict:
    malformed = [key for key in MAPPED_FIELDS if isinstance(item.get(key), dict | list)]
    if malformed:
        return {"_parsed": False, "parse_notes": f"Expected scalar fields: {', '.join(sorted(malformed))}", "metadata": item}
    raw_severity = str(item.get("severity", item.get("level", item.get("risk", "Informational")))).lower()
    severity = {
        "info": "Informational",
        "information": "Informational",
        "warning": "Medium",
        "warn": "Medium",
        "error": "High",
        "fatal": "Critical",
        "emergency": "Critical",
    }.get(raw_severity, raw_severity.title())
    action = str(item.get("event_type", item.get("action", item.get("operation", "Observed"))))
    denied = action.lower().replace(" ", "_") in {"login_failure", "denied", "blocked", "failed_login"}
    auth = authentication_action(action, item)
    is_auth = auth is not None
    status = auth[2] if auth else "Failure" if denied else "Success"
    activity_id, activity_name = {
        "create": (1, "Create"),
        "read": (2, "Read"),
        "update": (3, "Update"),
        "delete": (4, "Delete"),
    }.get(action.lower(), (99, action or "Other"))
    server = str(item.get("server") or "")
    try:
        server_ip = str(ip_address(server)) if server else ""
    except ValueError:
        server_ip = ""
    message = item.get("message", item.get("event"))
    if message is None:
        message = json.dumps(item, default=str)[:2000]
    return {
        "_parsed": True,
        "timestamp": str(item.get("timestamp", item.get("@timestamp", item.get("time", "")))),
        "timestamp_missing_ok": not any(key in item for key in ("timestamp", "@timestamp", "time")),
        "hostname": str(item.get("host", item.get("hostname", item.get("source", server))) or ""),
        "user": str(item.get("user", item.get("username", item.get("actor", ""))) or ""),
        "message": message,
        "severity": severity,
        "action": "Login Failure" if denied and is_auth else action,
        "disposition": "Failed" if status == "Failure" else status,
        "status": status,
        "src_endpoint_ip": item.get("src_ip", item.get("source_ip", item.get("client_ip", item.get("ip", "")))),
        "src_endpoint_port": item.get("src_port", item.get("source_port", item.get("client_port"))),
        "dst_endpoint_ip": item.get("dst_ip", item.get("destination_ip", server_ip)),
        "dst_endpoint_port": item.get("dst_port", item.get("destination_port", item.get("server_port"))),
        "device_vendor": str(item.get("vendor") or "Application"),
        "device_product": str(item.get("service", item.get("app")) or "application"),
        "metadata": {key: value for key, value in item.items() if key not in MAPPED_FIELDS},
        "ocsf_class": "Authentication" if is_auth else "API Activity",
        "class_uid": 3002 if is_auth else 6003,
        "category": "Identity & Access Management" if is_auth else "Application Activity",
        "category_uid": 3 if is_auth else 6,
        "activity_id": auth[0] if auth else activity_id,
        "activity_name": auth[1] if auth else activity_name,
    }


class JsonParser:
    name = "json"
    source_format = "json"
    version = "2.2.0"

    def detect(self, value: str) -> float:
        return 0.95 if value.lstrip().startswith("{") else 0.0

    def parse(self, value: str, observed_at: datetime) -> dict:
        try:
            item = decode_json(value)
        except ValueError as exc:
            return {"_parsed": False, "parse_notes": f"Invalid JSON: {exc}"}
        return (
            structured_record(item, observed_at)
            if isinstance(item, dict)
            else {"_parsed": False, "parse_notes": "JSON event must be an object"}
        )


class CsvRowParser:
    name = "csv"
    source_format = "csv"
    version = "1.1.0"

    def detect(self, value: str) -> float:
        return 0.0

    def parse(self, value: str, observed_at: datetime) -> dict:
        try:
            item = json.loads(value)
            return structured_record(item, observed_at) if isinstance(item, dict) else {"_parsed": False, "parse_notes": "CSV row must be an object"}
        except (TypeError, ValueError):
            return {"_parsed": False, "parse_notes": "Invalid normalized CSV row"}


class XmlEventParser:
    name = "xml"
    source_format = "xml"
    version = "1.2.0"

    def detect(self, value: str) -> float:
        return 0.8 if value.lstrip().startswith("<") and value.rstrip().endswith(">") else 0.0

    def parse(self, value: str, observed_at: datetime) -> dict:
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(value)
        except ET.ParseError:
            return {"_parsed": False, "parse_notes": "Invalid XML"}
        item = {}
        for child in root.iter():
            if child is root or len(child) != 0:
                continue
            key = child.attrib.get("Name") or child.tag.rsplit("}", 1)[-1]
            value = child.text or ""
            if key not in item:
                item[key] = value
            elif isinstance(item[key], list):
                item[key].append(value)
            else:
                item[key] = [item[key], value]
        if not item:
            return {"_parsed": False, "parse_notes": "XML event has no scalar fields"}
        return structured_record(item, observed_at)
