"""Deterministic synthetic inputs; no storage or network access."""

import json
from dataclasses import replace
from pathlib import Path

from ulpf.pipeline import run_payload

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ocsf-1.8.0"
OBSERVED_AT = "2026-09-01T00:01:00+00:00"


def cases():
    return json.loads((FIXTURES / "cases.json").read_text())


def export(case):
    events = run_payload(case["input"].encode(), case["filename"], source_id=f"fixture:{case['name']}")
    if len(events) != 1 or not events[0].parse_success or events[0].time_source != "source":
        raise ValueError(f"Fixture {case['name']} must produce one valid, explicitly timestamped event")
    # Fix only collection time; source time, parsed fields and identities remain untouched.
    return replace(events[0], observed_at=OBSERVED_AT).to_ocsf_dict()
