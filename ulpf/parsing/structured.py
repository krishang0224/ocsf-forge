"""Generic JSON, CSV-row, and XML-event parsers."""

import json
from datetime import datetime


def structured_record(item: dict, observed_at: datetime) -> dict:
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
    is_auth = any(token in action.lower() for token in ("login", "logon", "auth"))
    activity_id, activity_name = {
        "create": (1, "Create"),
        "read": (2, "Read"),
        "update": (3, "Update"),
        "delete": (4, "Delete"),
    }.get(action.lower(), (99, action or "Other"))
    return {
        "_parsed": True,
        "timestamp": str(item.get("timestamp", item.get("@timestamp", item.get("time", "")))),
        "timestamp_missing_ok": not any(key in item for key in ("timestamp", "@timestamp", "time")),
        "hostname": item.get("host", item.get("hostname", item.get("source", ""))),
        "user": item.get("user", item.get("username", item.get("actor", ""))),
        "message": item.get("message", item.get("event", json.dumps(item, default=str)[:2000])),
        "severity": severity,
        "action": "Login Failure" if denied and is_auth else action,
        "disposition": "Failed" if denied else "Success",
        "status": "Failure" if denied else "Success",
        "src_endpoint_ip": item.get("src_ip", item.get("source_ip", item.get("client_ip", item.get("ip", "")))),
        "src_endpoint_port": item.get("src_port", item.get("source_port", item.get("client_port"))),
        "dst_endpoint_ip": item.get("dst_ip", item.get("destination_ip", item.get("server", ""))),
        "dst_endpoint_port": item.get("dst_port", item.get("destination_port", item.get("server_port"))),
        "device_vendor": item.get("vendor", "Application"),
        "device_product": item.get("service", item.get("app", "application")),
        "metadata": item,
        "ocsf_class": "Authentication" if is_auth else "API Activity",
        "class_uid": 3002 if is_auth else 6003,
        "category": "Identity & Access Management" if is_auth else "Application Activity",
        "category_uid": 3 if is_auth else 6,
        "activity_id": 1 if is_auth else activity_id,
        "activity_name": "Logon" if is_auth else activity_name,
    }


class JsonParser:
    name = "json"
    source_format = "json"
    version = "2.0.0"

    def detect(self, value: str) -> float:
        try:
            return 0.95 if isinstance(json.loads(value), dict) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def parse(self, value: str, observed_at: datetime) -> dict:
        try:
            item = json.loads(value)
        except ValueError:
            return {"_parsed": False, "parse_notes": "Invalid JSON"}
        return (
            structured_record(item, observed_at)
            if isinstance(item, dict)
            else {"_parsed": False, "parse_notes": "JSON event must be an object"}
        )


class CsvRowParser:
    name = "csv"
    source_format = "csv"
    version = "1.0.0"

    def detect(self, value: str) -> float:
        return 0.0

    def parse(self, value: str, observed_at: datetime) -> dict:
        try:
            return structured_record(json.loads(value), observed_at)
        except (TypeError, ValueError):
            return {"_parsed": False, "parse_notes": "Invalid normalized CSV row"}


class XmlEventParser:
    name = "xml"
    source_format = "xml"
    version = "1.0.0"

    def detect(self, value: str) -> float:
        return 0.8 if value.lstrip().startswith("<") and value.rstrip().endswith(">") else 0.0

    def parse(self, value: str, observed_at: datetime) -> dict:
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(value)
        except ET.ParseError:
            return {"_parsed": False, "parse_notes": "Invalid XML"}
        item = {
            child.tag.rsplit("}", 1)[-1]: child.text or ""
            for child in root.iter()
            if child is not root and len(child) == 0
        }
        if not item:
            return {"_parsed": False, "parse_notes": "XML event has no scalar fields"}
        return structured_record(item, observed_at)
