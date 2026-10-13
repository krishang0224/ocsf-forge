"""Bounded parser, document, preview and detection stress probes; no services."""

import argparse
import json
import random
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from time import perf_counter

from benchmarks.homelab import measure
from ulpf.detection.config import DetectionSettings
from ulpf.detection.models import AuthenticationEvent
from ulpf.detection.rules import evaluate
from ulpf.parsing.limits import InputLimitError
from ulpf.pipeline import events_to_frame, run_payload, run_pipeline
from ulpf.sample_data import SAMPLE_LOGS


def mixed(count):
    events = run_pipeline([SAMPLE_LOGS[i % len(SAMPLE_LOGS)] for i in range(count)], source_id="stress-mixed")
    assert len(events) == count and all(event.parse_success for event in events)
    assert len({event.event_id for event in events}) == count
    return {"events": count}


def malformed(count):
    rng = random.Random(20261013)
    fields = ["timestamp", "message", "user", "host", "severity", "src_port", "dst_ip", "action"]
    values = [None, True, False, -1, 0, 1.5, "", "unknown", [], {}, ["nested"], {"nested": 1}]
    lines = [json.dumps({key: rng.choice(values) for key in rng.sample(fields, 4)}) for _ in range(count)]
    events = run_pipeline(lines)
    for line, event in zip(lines, events, strict=True):
        assert event.original_raw_payload == line
        json.dumps(event.to_ocsf_dict(), allow_nan=False)
    assert len(events) == count
    return {"events": count, "quarantined": sum(not event.parse_success for event in events)}


def limits():
    try:
        run_payload(b"{}\n" * 1_000_000, "million.jsonl", max_events=50000)
    except InputLimitError:
        pass
    else:
        raise AssertionError("Oversized document was not rejected")
    xml = ("<event>" * 2000 + "x" + "</event>" * 2000).encode()
    event, = run_payload(xml, "deep.xml", max_events=50000)
    assert not event.parse_success and event.original_raw_payload.encode() == xml
    return {"record_budget": 50000, "oversized_jsonl_records": 1000000, "xml_depth": 2000}


def preview():
    event = run_pipeline([json.dumps({"message": "preview", "extra": list(range(10000))})])[0]
    events = [event] * 1000
    columns = ["timestamp", "severity", "message", "raw_payload_hash"]
    start = perf_counter()
    reference = events_to_frame(events)[columns]
    reference_seconds = perf_counter() - start
    start = perf_counter()
    projected = events_to_frame(events, columns=columns)
    projected_seconds = perf_counter() - start
    assert reference.equals(projected)
    return {"records": 1000, "extra_values_per_record": 10000,
            "full_conversion_seconds": round(reference_seconds, 6),
            "projected_seconds": round(projected_seconds, 6)}


def detection(count, pattern):
    start = datetime(2026, 10, 13, tzinfo=UTC)
    events = [AuthenticationEvent(str(i), start + timedelta(microseconds=i), "host", "ssh",
                                  str(IPv4Address(0x0A000000 + i)) if pattern == "distinct-sources" else "192.0.2.1",
                                  str(i) if pattern == "spray" else "alice", 2) for i in range(count)]
    findings = evaluate(events, start, start + timedelta(seconds=max(1, count / 1_000_000)),
                        DetectionSettings(max_events=count))
    expected = [] if pattern == "distinct-sources" else ["auth.password_spray" if pattern == "spray" else "auth.repeated_failures"]
    assert sorted(finding.rule_id for finding in findings) == expected
    return {"events": count, "findings": len(findings)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", nargs="+", type=int, default=[50000, 100000, 250000])
    parser.add_argument("--malformed-rows", type=int, default=100000)
    parser.add_argument("--detection-rows", type=int, default=100000)
    parser.add_argument("--isolate", action="store_true", help="run each workload in a child so a killed case cannot stop the audit")
    parser.add_argument("--case", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(*args.rows, args.malformed_rows, args.detection_rows) < 5 or args.detection_rows >= 300_000_000:
        parser.error("row counts must be at least five; detection must stay within one window")
    operations = {f"mixed-parsing-{count}": lambda count=count: mixed(count) for count in args.rows}
    operations.update({"malformed-field-corpus": lambda: malformed(args.malformed_rows),
                       "document-limits": limits, "preview-projection": preview})
    for pattern in ("hot-user", "spray", "distinct-sources"):
        operations[f"detection-{pattern}"] = lambda pattern=pattern: detection(args.detection_rows, pattern)
    if args.case:
        if args.case not in operations:
            parser.error("Unknown workload")
        return 0 if measure(args.case, operations[args.case]) else 1
    checks = []
    for name, operation in operations.items():
        if not args.isolate:
            checks.append(measure(name, operation))
            continue
        command = [sys.executable, "-m", "benchmarks.pipeline", "--rows", *map(str, args.rows),
                   "--malformed-rows", str(args.malformed_rows), "--detection-rows", str(args.detection_rows),
                   "--case", name]
        try:
            child = subprocess.run(command, capture_output=True, text=True, timeout=180)
            if child.stdout:
                print(child.stdout, end="", flush=True)
            if child.returncode:
                print(json.dumps({"case": name, "ok": False, "child_exit_code": child.returncode,
                                  "error": child.stderr[-2000:]}), flush=True)
            checks.append(child.returncode == 0)
        except subprocess.TimeoutExpired:
            print(json.dumps({"case": name, "ok": False, "timeout_seconds": 180}), flush=True)
            checks.append(False)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
