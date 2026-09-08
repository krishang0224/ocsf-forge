"""Confidence-based parser discovery."""

from datetime import UTC, datetime

from ulpf.parsing.base import LogParser
from ulpf.parsing.security import CefParser, LeefParser
from ulpf.parsing.structured import CsvRowParser, JsonParser, XmlEventParser
from ulpf.parsing.text import ApacheParser, Log4jParser, SyslogParser


class ParserRegistry:
    def __init__(self, parsers: list[LogParser] | None = None):
        self.parsers = parsers or []

    def register(self, parser: LogParser) -> None:
        self.parsers.append(parser)

    def parse(
        self, value: str, observed_at: datetime | None = None, forced_format: str | None = None
    ) -> tuple[str, str, str, float, dict]:
        observed = observed_at or datetime.now(UTC)
        candidates = [
            parser for parser in self.parsers if forced_format is None or parser.source_format == forced_format
        ]
        confidence, parser = max(
            ((parser.detect(value), parser) for parser in candidates), key=lambda item: item[0], default=(0.0, None)
        )
        if parser is None or (forced_format is None and confidence <= 0):
            return (
                "unknown",
                "unknown",
                "1.0.0",
                0.0,
                {"_parsed": False, "parse_notes": "No parser recognized the event"},
            )
        try:
            parsed = parser.parse(value, observed)
        except (ValueError, TypeError, OverflowError, RecursionError) as exc:
            parsed = {"_parsed": False, "parse_notes": f"Invalid {parser.name} event: {type(exc).__name__}: {str(exc)[:200]}"}
        parsed.setdefault("_parsed", False)
        return parser.source_format, parser.name, parser.version, confidence, parsed


default_registry = ParserRegistry(
    [
        Log4jParser(),
        CefParser(),
        LeefParser(),
        JsonParser(),
        ApacheParser(),
        SyslogParser(),
        XmlEventParser(),
        CsvRowParser(),
    ]
)
