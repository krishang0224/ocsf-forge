"""Text parsers for Syslog, web access logs, and Log4j."""

import re
from datetime import UTC, datetime


class Log4jParser:
    name = "log4j"
    source_format = "log4j"
    version = "1.1.0"
    pattern = re.compile(
        r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2},\d{3})\s+"
        r"(?P<level>TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s+"
        r"\[(?P<thread>[^\]]+)]\s+(?P<logger>[\w.$]+):\s*(?P<msg>.*)$",
        re.S,
    )
    levels = {
        "FATAL": "Critical",
        "ERROR": "High",
        "WARN": "Medium",
        "INFO": "Informational",
        "DEBUG": "Informational",
        "TRACE": "Informational",
    }

    def detect(self, value: str) -> float:
        return 0.9 if self.pattern.match(value.strip()) else 0.0

    def parse(self, value: str, observed_at: datetime) -> dict:
        match = self.pattern.match(value.strip())
        if not match:
            return {"_parsed": False, "parse_notes": "Malformed Log4j event"}
        item = match.groupdict()
        level = item["level"]
        is_error = level in {"ERROR", "FATAL"}
        return {
            "_parsed": True,
            "timestamp": f"{item['date']}T{item['time'].replace(',', '.')}Z",
            "message": item["msg"],
            "severity": self.levels[level],
            "action": "Error" if level in {"ERROR", "FATAL"} else "Observed",
            "disposition": "Failed" if level in {"ERROR", "FATAL"} else "Success",
            "status": "Failure" if level in {"ERROR", "FATAL"} else "Success",
            "device_product": item["logger"].rsplit(".", 1)[-1],
            "metadata": {"thread": item["thread"], "logger": item["logger"], "level": level},
            "ocsf_class": "Application Error" if is_error else "API Activity",
            "class_uid": 6008 if is_error else 6003,
            "category": "Application Activity",
            "category_uid": 6,
            "activity_id": 1 if is_error else 99,
            "activity_name": "General Error" if is_error else "Log Message",
        }


class ApacheParser:
    name = "apache"
    source_format = "apache"
    version = "1.1.0"
    pattern = re.compile(
        r"^(?P<ip>\S+)\s+\S+\s+(?P<user>\S+)\s+\[(?P<ts>[^]]+)]\s+"
        r'"(?P<method>\S+)\s+(?P<path>\S+)\s+(?P<proto>[^\"]+)"\s+'
        r'(?P<status>\d{3})\s+(?P<bytes>\d+|-)(?:\s+"(?P<ref>[^\"]*)"(?:\s+"(?P<ua>[^\"]*)")?)?$'
    )
    activities = {
        "CONNECT": (1, "Connect"),
        "DELETE": (2, "Delete"),
        "GET": (3, "Get"),
        "HEAD": (4, "Head"),
        "OPTIONS": (5, "Options"),
        "POST": (6, "Post"),
        "PUT": (7, "Put"),
        "TRACE": (8, "Trace"),
        "PATCH": (9, "Patch"),
    }

    def detect(self, value: str) -> float:
        return 0.92 if self.pattern.match(value.strip()) else 0.0

    def parse(self, value: str, observed_at: datetime) -> dict:
        match = self.pattern.match(value.strip())
        if not match:
            return {"_parsed": False, "parse_notes": "Malformed access log"}
        item = match.groupdict()
        status = int(item["status"])
        activity_id, activity_name = self.activities.get(item["method"].upper(), (99, "Other"))
        try:
            timestamp = datetime.strptime(item["ts"], "%d/%b/%Y:%H:%M:%S %z").isoformat()
        except ValueError:
            timestamp = item["ts"]
        return {
            "_parsed": True,
            "timestamp": timestamp,
            "message": f"{item['method']} {item['path']} → {status}",
            "src_endpoint_ip": item["ip"],
            "user": "" if item["user"] == "-" else item["user"],
            "severity": "High" if status >= 500 else "Low" if status >= 400 else "Informational",
            "action": item["method"].title(),
            "disposition": "Denied" if status in {401, 403} else "Allowed",
            "status": "Failure" if status >= 400 else "Success",
            "device_product": "httpd",
            "metadata": {
                "http_status": status,
                "bytes": int(item["bytes"]) if item["bytes"].isdigit() else None,
                "path": item["path"],
                "protocol": item["proto"],
                "referer": item.get("ref") or "",
                "user_agent": item.get("ua") or "",
            },
            "ocsf_class": "HTTP Activity",
            "class_uid": 4002,
            "category": "Network Activity",
            "category_uid": 4,
            "activity_id": activity_id,
            "activity_name": activity_name,
        }


class SyslogParser:
    name = "syslog"
    source_format = "syslog"
    version = "2.1.1"
    rfc5424 = re.compile(
        r"^<(?P<pri>\d{1,3})>(?P<version>\d+)\s+(?P<ts>\S+)\s+(?P<host>\S+)\s+(?P<app>\S+)\s+(?P<pid>\S+)\s+(?P<msgid>\S+)\s+(?P<structured>(?:-|\[.*?]))(?:\s+(?P<msg>.*))?$",
        re.S,
    )
    rfc3164 = re.compile(
        r"^(?P<pri><\d+>)?(?P<ts>(?P<mon>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s(?P<time>\d{2}:\d{2}:\d{2}))\s+(?P<host>\S+)\s+(?P<tag>[\w\-/.]+)?(?:\[(?P<pid>\d+)])?:\s*(?P<msg>.*)$",
        re.S,
    )
    key_values = re.compile(r'(?<![\w.-])([\w.-]+)=("(?:\\.|[^"\\])*"|\S+)')

    def detect(self, value: str) -> float:
        text = value.strip()
        if self.rfc5424.match(text):
            return 0.96
        return 0.82 if self.rfc3164.match(text) else 0.0

    @staticmethod
    def _nearest_year(timestamp: str, observed_at: datetime) -> datetime:
        candidates = []
        for year in (observed_at.year - 1, observed_at.year, observed_at.year + 1):
            try:
                candidates.append(datetime.strptime(f"{year} {timestamp}", "%Y %b %d %H:%M:%S").replace(tzinfo=observed_at.tzinfo or UTC))
            except ValueError:
                continue
        if not candidates:
            raise ValueError("Invalid RFC3164 timestamp")
        return min(candidates, key=lambda item: abs((item - observed_at).total_seconds()))

    def parse(self, value: str, observed_at: datetime) -> dict:
        text = value.strip()
        match = self.rfc5424.match(text)
        if match:
            item = match.groupdict()
            timestamp = "" if item["ts"] == "-" else item["ts"]
            message = item.get("msg") or ""
            app = item["app"]
            extra = {
                "rfc": 5424,
                "priority": int(item["pri"]),
                "version": item["version"],
                "pid": item["pid"],
                "message_id": item["msgid"],
                "structured_data": item["structured"],
            }
        else:
            match = self.rfc3164.match(text)
            if not match:
                return {"_parsed": False, "parse_notes": "Malformed Syslog event"}
            item = match.groupdict()
            timestamp = self._nearest_year(item["ts"], observed_at).isoformat()
            message = item.get("msg") or ""
            app = item.get("tag") or "syslog"
            extra = {"rfc": 3164, "priority": int((item.get("pri") or "<13>")[1:-1]), "pid": item.get("pid")}
        kv = {
            key: (field[1:-1] if field.startswith('"') and field.endswith('"') else field).replace('\\"', '"')
            for key, field in self.key_values.findall(message)
        }
        lowered = message.lower()
        denied = any(word in lowered for word in ("deny", "drop", "block", "reject"))
        return {
            "_parsed": True,
            "timestamp": timestamp,
            "timestamp_missing_ok": not timestamp,
            "hostname": item["host"],
            "message": message,
            "severity": "Critical"
            if denied and any(word in lowered for word in ("critical", "attack"))
            else "Medium"
            if denied
            else "Informational",
            "action": "Refuse" if denied else "Open" if "allow" in lowered else "Traffic",
            "disposition": "Blocked" if denied else "Allowed",
            "status": "Failure" if denied else "Success",
            "src_endpoint_ip": kv.get("src") or kv.get("srcip") or kv.get("src_ip", ""),
            "dst_endpoint_ip": kv.get("dst") or kv.get("dstip") or kv.get("dst_ip", ""),
            "src_endpoint_port": kv.get("sport"),
            "dst_endpoint_port": kv.get("dport"),
            "device_product": kv.get("deviceProduct") or app,
            "metadata": {**extra, **kv},
            "ocsf_class": "Network Activity",
            "class_uid": 4001,
            "category": "Network Activity",
            "category_uid": 4,
            "activity_id": 5 if denied else 1 if "allow" in lowered else 6,
            "activity_name": "Refuse" if denied else "Open" if "allow" in lowered else "Traffic",
        }
