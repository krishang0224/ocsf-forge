"""Offline evaluation commands; no database or object-storage connections."""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ulpf.detection.demo import demo_logs
from ulpf.detection.models import AuthenticationEvent
from ulpf.detection.rules import evaluate
from ulpf.pipeline import run_payload, run_pipeline


def _emit(value, stream):
    print(json.dumps(value, separators=(",", ":"), allow_nan=False), file=stream)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect log normalization and authentication findings without Docker.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Emit findings from 15 synthetic authentication events")
    normalize = commands.add_parser("normalize", help="Emit valid OCSF JSONL; report rejected records on stderr")
    normalize.add_argument("input", help="Input file, or - for standard input")
    normalize.add_argument("--max-bytes", type=int, default=25 * 1024 * 1024, help="Input limit (default: 25 MiB)")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            end = datetime.now(UTC)
            events = run_pipeline(demo_logs(end), source_id="offline-demo", observed_at=end)
            auth = [AuthenticationEvent(
                event.event_id, datetime.fromisoformat(event.timestamp), event.hostname, event.device_product,
                event.src_endpoint_ip, event.user, event.status_id, event.class_uid, event.activity_id,
            ) for event in events if event.parse_success and event.timestamp]
            findings = evaluate(auth, end - timedelta(minutes=10), end, detected_at=end)
            for finding in findings:
                _emit(finding.to_ocsf_dict(), sys.stdout)
            _emit({"events": len(events), "findings": len(findings), "synthetic": True}, sys.stderr)
            return 0
        if args.max_bytes <= 0:
            parser.error("--max-bytes must be positive")
        if args.input == "-":
            payload = sys.stdin.buffer.read(args.max_bytes + 1)
            filename = "stdin.log"
        else:
            with Path(args.input).open("rb") as stream:
                payload = stream.read(args.max_bytes + 1)
            filename = Path(args.input).name
        if len(payload) > args.max_bytes:
            raise ValueError(f"Input exceeds {args.max_bytes} bytes; no records processed")
        events = run_payload(payload, filename)
        rejected = 0
        for event in events:
            if event.parse_success:
                _emit(event.to_ocsf_dict(), sys.stdout)
            else:
                rejected += 1
                _emit({"event_id": event.event_id, "source_offset": event.source_offset,
                       "error": event.parse_notes}, sys.stderr)
        _emit({"events": len(events), "accepted": len(events) - rejected, "rejected": rejected}, sys.stderr)
        return 1 if rejected else 0
    except (OSError, ValueError) as exc:
        print(f"ocsf-forge: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
