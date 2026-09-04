"""Format detection and lossless parsing for common enterprise logs."""

import json
import re
from datetime import UTC, datetime


class LogParserEngine:
    RE_LOG4J = re.compile(
        r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2}:\d{2},\d{3})\s+"
        r"(?P<level>TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s+"
        r"\[(?P<thread>[^\]]+)]\s+(?P<logger>[\w.$]+):\s*(?P<msg>.*)$"
    )
    RE_SYSLOG = re.compile(
        r"^(?P<pri><\d+>)?(?P<ts>(?P<mon>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s"
        r"(?P<time>\d{2}:\d{2}:\d{2}))\s+(?P<host>\S+)\s+(?P<tag>[\w\-/.]+)?"
        r"(?:\[(?P<pid>\d+)])?:\s*(?P<msg>.*)$"
    )
    RE_KV = re.compile(r"(\w+)=(\"[^\"]*\"|\S+)")
    RE_APACHE = re.compile(
        r"^(?P<ip>\S+)\s+\S+\s+(?P<user>\S+)\s+\[(?P<ts>[^]]+)]\s+"
        r'"(?P<method>\S+)\s+(?P<path>\S+)\s+(?P<proto>[^\"]+)"\s+'
        r'(?P<status>\d{3})\s+(?P<bytes>\d+|-)(?:\s+"(?P<ref>[^\"]*)"'
        r'(?:\s+"(?P<ua>[^\"]*)")?)?$'
    )
    RE_CEF = re.compile(
        r"^CEF:(?P<ver>\d+)\|(?P<vendor>[^|]*)\|(?P<product>[^|]*)\|"
        r"(?P<dversion>[^|]*)\|(?P<sigid>[^|]*)\|(?P<name>[^|]*)\|"
        r"(?P<severity>[^|]*)\|(?P<ext>.*)$"
    )
    RE_CEF_EXT = re.compile(r"(\S+)=((?:(?!\s+\S+=).)*)")
    LOG4J_SEVERITY = {
        "FATAL": "Critical",
        "ERROR": "High",
        "WARN": "Medium",
        "INFO": "Informational",
        "DEBUG": "Informational",
        "TRACE": "Informational",
    }

    def detect_format(self, line: str) -> str:
        value = line.strip()
        if not value:
            return "empty"
        if self.RE_LOG4J.match(value):
            return "log4j"
        if value.startswith("CEF:"):
            return "cef"
        try:
            if isinstance(json.loads(value), dict):
                return "json"
        except (ValueError, TypeError):
            pass
        if self.RE_APACHE.match(value):
            return "apache"
        if value.startswith("<") or self.RE_SYSLOG.match(value):
            return "syslog"
        return "unknown"

    def parse_line(self, line: str) -> tuple[str, dict]:
        fmt = self.detect_format(line)
        parser = getattr(self, f"parse_{fmt}", None)
        parsed = parser(line) if parser else {"_parsed": False}
        parsed.setdefault("_parsed", False)
        return fmt, parsed

    def parse_log4j(self, line: str) -> dict:
        match = self.RE_LOG4J.match(line.strip())
        if not match:
            return {"_parsed": False}
        item = match.groupdict()
        level = item["level"]
        return {
            "_parsed": True,
            "timestamp": f"{item['date']}T{item['time'].replace(',', '.')}Z",
            "message": item["msg"],
            "severity": self.LOG4J_SEVERITY[level],
            "action": "Error" if level in {"ERROR", "FATAL"} else "Observed",
            "disposition": "Failed" if level in {"ERROR", "FATAL"} else "Success",
            "device_product": item["logger"].rsplit(".", 1)[-1],
            "metadata": {"thread": item["thread"], "logger": item["logger"], "level": level},
        }

    def parse_syslog(self, line: str) -> dict:
        match = self.RE_SYSLOG.match(line.strip())
        if not match:
            return {"_parsed": False}
        item = match.groupdict()
        kv = {key: value.strip('"') for key, value in self.RE_KV.findall(item["msg"] or "")}
        message = (item["msg"] or "").lower()
        denied = any(word in message for word in ("deny", "drop", "block", "reject"))
        severity = (
            "Critical"
            if denied and any(word in message for word in ("critical", "attack"))
            else "Medium"
            if denied
            else "Informational"
        )
        return {
            "_parsed": True,
            "timestamp": datetime.strptime(f"{datetime.now(UTC).year} {item['ts']}", "%Y %b %d %H:%M:%S")
            .replace(tzinfo=UTC)
            .isoformat(),
            "hostname": item["host"],
            "message": item["msg"],
            "severity": severity,
            "action": "Denied" if denied else "Allowed" if "allow" in message else "Observed",
            "disposition": "Blocked" if denied else "Allowed",
            "src_endpoint_ip": kv.get("src") or kv.get("srcip") or kv.get("src_ip", ""),
            "dst_endpoint_ip": kv.get("dst") or kv.get("dstip") or kv.get("dst_ip", ""),
            "src_endpoint_port": self._port(kv.get("sport")),
            "dst_endpoint_port": self._port(kv.get("dport")),
            "device_product": kv.get("deviceProduct") or item.get("tag") or "syslog",
            "metadata": kv,
        }

    def parse_apache(self, line: str) -> dict:
        match = self.RE_APACHE.match(line.strip())
        if not match:
            return {"_parsed": False}
        item = match.groupdict()
        status = int(item["status"])
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
            "action": "Denied" if status in {401, 403} else "Allowed",
            "disposition": "Denied" if status in {401, 403} else "Allowed",
            "status": f"HTTP {status}",
            "device_product": "httpd",
            "metadata": {
                "http_status": status,
                "bytes": int(item["bytes"]) if item["bytes"].isdigit() else None,
                "path": item["path"],
                "referer": item.get("ref") or "",
                "user_agent": item.get("ua") or "",
            },
        }

    def parse_cef(self, line: str) -> dict:
        match = self.RE_CEF.match(line.strip())
        if not match:
            return {"_parsed": False}
        item = match.groupdict()
        ext = {key: value.strip() for key, value in self.RE_CEF_EXT.findall(item["ext"])}
        try:
            level = int(item["severity"])
            severity = "Critical" if level >= 9 else "High" if level >= 7 else "Medium" if level >= 4 else "Low"
        except ValueError:
            severity = item["severity"].title()
        return {
            "_parsed": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "hostname": ext.get("dhost", ext.get("dvchost", "")),
            "device_vendor": item["vendor"],
            "device_product": item["product"],
            "message": item["name"],
            "severity": severity,
            "action": ext.get("act", "Detected"),
            "disposition": ext.get("outcome", "Suspicious"),
            "src_endpoint_ip": ext.get("src", ""),
            "dst_endpoint_ip": ext.get("dst", ""),
            "user": ext.get("suser", ext.get("duser", "")),
            "metadata": ext,
        }

    def parse_json(self, line: str) -> dict:
        try:
            item = json.loads(line.strip())
        except ValueError:
            return {"_parsed": False}
        raw_severity = str(item.get("severity", item.get("level", item.get("risk", "Informational")))).lower()
        severity = {
            "info": "Informational",
            "warning": "Medium",
            "warn": "Medium",
            "error": "High",
            "fatal": "Critical",
        }.get(raw_severity, raw_severity.title())
        action = str(item.get("event_type", item.get("action", "Observed")))
        denied = action.lower() in {"login_failure", "denied", "blocked", "failed_login"}
        return {
            "_parsed": True,
            "timestamp": str(item.get("timestamp", item.get("@timestamp", item.get("time", "")))),
            "hostname": item.get("host", item.get("source", "")),
            "user": item.get("user", item.get("username", item.get("actor", ""))),
            "message": item.get("message", item.get("event", json.dumps(item)[:500])),
            "severity": severity,
            "action": action,
            "disposition": "Failed" if denied else "Success",
            "src_endpoint_ip": item.get("src_ip", item.get("client_ip", item.get("ip", ""))),
            "dst_endpoint_ip": item.get("dst_ip", item.get("server", "")),
            "device_vendor": item.get("vendor", "Application"),
            "device_product": item.get("service", item.get("app", "application")),
            "metadata": item,
        }

    @staticmethod
    def _port(value: str | None) -> int | None:
        try:
            return int(value) if value else None
        except ValueError:
            return None
