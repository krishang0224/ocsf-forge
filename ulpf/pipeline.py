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


def _logical_events(lines: list[str] | tuple[str, ...]) -> list[tuple[int, str]]:
    events: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        continuation = bool(events) and (
            line[:1].isspace() or stripped.startswith(("at ", "Caused by:", "Suppressed:"))
        )
        if continuation:
            offset, existing = events[-1]
            events[-1] = (offset, f"{existing}\n{line}")
        elif line.strip():
            events.append((index, line))
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
    if isinstance(lines, str):
        lines = lines.splitlines()
    parser = LogParserEngine()
    normalizer = OCSFNormalizer()
    observed = observed_at or datetime.now(UTC)
    events: list[NormalizedEvent] = []
    for offset, line in _logical_events(lines):
        if forced_format:
            fmt, parser_name, parser_version, confidence, parsed = parser.registry.parse(line, observed, forced_format)
            parsed.update(
                {"_parser_name": parser_name, "_parser_version": parser_version, "_detection_confidence": confidence}
            )
        else:
            fmt, parsed = parser.parse_line(line, observed)
        events.append(
            normalizer.normalize(
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
    if lowered.endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(text)))
        lines = [json.dumps(row, separators=(",", ":"), ensure_ascii=False) for row in rows]
        return run_pipeline(lines, source_id=identity, source_name=filename, forced_format="csv")
    if lowered.endswith(".xml"):
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return run_pipeline([text], source_id=identity, source_name=filename, forced_format="xml")
        nodes = list(root) or [root]
        lines = [ET.tostring(node, encoding="unicode") for node in nodes]
        return run_pipeline(lines, source_id=identity, source_name=filename, forced_format="xml")
    if lowered.endswith(".json"):
        try:
            decoded = json.loads(text)
            if isinstance(decoded, list):
                lines = [json.dumps(item, separators=(",", ":"), ensure_ascii=False) for item in decoded]
                return run_pipeline(lines, source_id=identity, source_name=filename, forced_format="json")
        except ValueError:
            pass
    return run_pipeline(text.splitlines(), source_id=identity, source_name=filename)


def events_to_frame(events: list[NormalizedEvent], include_raw: bool = False) -> pd.DataFrame:
    rows = []
    for event in events:
        row = event.to_dict()
        if not include_raw:
            row.pop("original_raw_payload", None)
        rows.append(row)
    return pd.DataFrame(rows)
