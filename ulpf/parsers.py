"""Backward-compatible facade over the versioned parser registry."""

from datetime import UTC, datetime

from ulpf.parsing import default_registry


class LogParserEngine:
    def __init__(self, registry=default_registry):
        self.registry = registry

    def detect_format(self, line: str) -> str:
        return self.registry.parse(line)[0] if line.strip() else "empty"

    def parse_line(self, line: str, observed_at: datetime | None = None) -> tuple[str, dict]:
        source_format, parser_name, parser_version, confidence, parsed = self.registry.parse(line, observed_at)
        parsed["_parser_name"] = parser_name
        parsed["_parser_version"] = parser_version
        parsed["_detection_confidence"] = confidence
        return source_format, parsed

    def _parse_as(self, line: str, source_format: str) -> dict:
        return self.registry.parse(line, datetime.now(UTC), source_format)[-1]

    def parse_json(self, line: str) -> dict:
        return self._parse_as(line, "json")

    def parse_syslog(self, line: str) -> dict:
        return self._parse_as(line, "syslog")

    def parse_apache(self, line: str) -> dict:
        return self._parse_as(line, "apache")

    def parse_cef(self, line: str) -> dict:
        return self._parse_as(line, "cef")

    def parse_leef(self, line: str) -> dict:
        return self._parse_as(line, "leef")

    def parse_log4j(self, line: str) -> dict:
        return self._parse_as(line, "log4j")
