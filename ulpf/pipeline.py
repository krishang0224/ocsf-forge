"""Pure ingestion pipeline functions shared by UI and tests."""

import pandas as pd

from ulpf.models import NormalizedEvent
from ulpf.normalizer import OCSFNormalizer
from ulpf.parsers import LogParserEngine


def run_pipeline(lines: list[str] | tuple[str, ...]) -> list[NormalizedEvent]:
    parser = LogParserEngine()
    normalizer = OCSFNormalizer()
    events: list[NormalizedEvent] = []
    for line in lines:
        if line.strip():
            fmt, parsed = parser.parse_line(line)
            events.append(normalizer.normalize(line, fmt, parsed))
    return events


def events_to_frame(events: list[NormalizedEvent], include_raw: bool = False) -> pd.DataFrame:
    rows = []
    for event in events:
        row = event.to_dict()
        if not include_raw:
            row.pop("original_raw_payload", None)
        rows.append(row)
    return pd.DataFrame(rows)
