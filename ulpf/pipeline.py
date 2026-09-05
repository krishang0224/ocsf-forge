"""Pure ingestion pipeline functions shared by UI, workers, and tests."""

import csv
import hashlib
import io
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pandas as pd

from ulpf.models import NormalizedEvent
from ulpf.normalizer import OCSFNormalizer
from ulpf.parsers import LogParserEngine

CSV_FIELDS = {
    "@timestamp",
    "action",
    "event",
    "event_type",
    "host",
    "hostname",
    "level",
    "message",
    "severity",
    "source_ip",
    "src_ip",
    "time",
    "timestamp",
    "user",
    "username",
}


def _logical_events(lines: list[str] | tuple[str, ...], is_log4j) -> list[tuple[int, str]]:
    events: list[tuple[int, str]] = []
    accepts_continuations = False
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        continuation = accepts_continuations and bool(events) and (
            line[:1].isspace() or stripped.startswith(("at ", "Caused by:", "Suppressed:"))
        )
        if continuation:
            offset, existing = events[-1]
            events[-1] = (offset, f"{existing}\n{line}")
        elif line.strip():
            events.append((index, line))
            accepts_continuations = is_log4j(line)
    return events


def run_pipeline(
    lines: str | list[str] | tuple[str, ...],
    *,
    source_id: str = "interactive",
    source_name: str = "",
    source_offset_start: int = 0,
    ingestion_run_id: str = "",
    observed_at: datetime | None = None,
    forced_format: str | None = None,
) -> list[NormalizedEvent]:
    return EventProcessor().run(
        lines,
        source_id=source_id,
        source_name=source_name,
        source_offset_start=source_offset_start,
        ingestion_run_id=ingestion_run_id,
        observed_at=observed_at,
        forced_format=forced_format,
    )


class EventProcessor:
    """Reusable parser and normalizer for long-running ingestion workers."""

    def __init__(self) -> None:
        self.parser = LogParserEngine()
        self.normalizer = OCSFNormalizer()
        self.log4j_parser = next(
            parser for parser in self.parser.registry.parsers if parser.source_format == "log4j"
        )

    def run(
        self,
        lines: str | list[str] | tuple[str, ...],
        *,
        source_id: str = "interactive",
        source_name: str = "",
        source_offset_start: int = 0,
        ingestion_run_id: str = "",
        observed_at: datetime | None = None,
        forced_format: str | None = None,
    ) -> list[NormalizedEvent]:
        if isinstance(lines, str):
            lines = lines.splitlines()
        observed = observed_at or datetime.now(UTC)
        events: list[NormalizedEvent] = []
        for offset, line in _logical_events(lines, lambda value: self.log4j_parser.detect(value) > 0):
            if forced_format:
                fmt, parser_name, parser_version, confidence, parsed = self.parser.registry.parse(
                    line, observed, forced_format
                )
                parsed.update(
                    {
                        "_parser_name": parser_name,
                        "_parser_version": parser_version,
                        "_detection_confidence": confidence,
                    }
                )
            else:
                fmt, parsed = self.parser.parse_line(line, observed)
            events.append(
                self.normalizer.normalize(
                    line,
                    fmt,
                    parsed,
                    observed_at=observed,
                    source_id=source_id,
                    source_offset=source_offset_start + offset,
                    source_name=source_name,
                    ingestion_run_id=ingestion_run_id,
                )
            )
        return events


def run_payload(payload: bytes, filename: str = "upload.log", source_id: str | None = None) -> list[NormalizedEvent]:
    text = payload.decode("utf-8", errors="replace")
    identity = source_id or hashlib.sha256(payload).hexdigest()
    lowered = filename.lower()
    try:
        decoded = json.loads(text)
    except ValueError:
        decoded = None
    if isinstance(decoded, dict | list):
        records = decoded if isinstance(decoded, list) else [decoded]
        lines = [json.dumps(item, separators=(",", ":"), ensure_ascii=False) for item in records]
        return run_pipeline(lines, source_id=identity, source_name=filename, forced_format="json")
    if lowered.endswith(".xml") or text.lstrip().startswith("<"):
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return run_pipeline([text], source_id=identity, source_name=filename, forced_format="xml")
        root_name = root.tag.rsplit("}", 1)[-1].lower()
        nodes = list(root) if root_name in {"events", "logs", "records"} and list(root) else [root]
        lines = [ET.tostring(node, encoding="unicode") for node in nodes]
        return run_pipeline(lines, source_id=identity, source_name=filename, forced_format="xml")
    if lowered.endswith(".csv") or _looks_like_csv(text):
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = [_normalize_csv_row(row) for row in csv.DictReader(io.StringIO(text), dialect=dialect)]
        lines = [json.dumps(row, separators=(",", ":"), ensure_ascii=False) for row in rows]
        return run_pipeline(lines, source_id=identity, source_name=filename, forced_format="csv")
    return run_pipeline(text.splitlines(), source_id=identity, source_name=filename)


def _looks_like_csv(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=",;\t")
        header = next(csv.reader([lines[0]], dialect=dialect))
    except (csv.Error, StopIteration):
        return False
    return bool({name.strip().lstrip("\ufeff").lower() for name in header} & CSV_FIELDS)


def _normalize_csv_row(row: dict[str | None, str | list[str] | None]) -> dict:
    normalized = {}
    for key, value in row.items():
        cleaned = (key or "").strip().lstrip("\ufeff")
        normalized[cleaned.lower() if cleaned.lower() in CSV_FIELDS else cleaned] = value
    return normalized


def events_to_frame(events: list[NormalizedEvent], include_raw: bool = False) -> pd.DataFrame:
    rows = []
    for event in events:
        row = event.to_dict()
        if not include_raw:
            row.pop("original_raw_payload", None)
        rows.append(row)
    return pd.DataFrame(rows)
