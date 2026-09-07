"""Poll authentication events and persist locally generated findings."""

import argparse
import json
import logging
import signal
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic, time

from ulpf.config import settings
from ulpf.detection.config import DetectionSettings
from ulpf.detection.rules import evaluate
from ulpf.detection.store import DetectionStore

LOGGER = logging.getLogger(__name__)
HEARTBEAT = Path("/tmp/ocsf-detection-last-success")


def healthy(config: DetectionSettings) -> bool:
    try:
        age = time() - float(HEARTBEAT.read_text())
        return 0 <= age <= config.interval_seconds * 3 + 30
    except (OSError, ValueError):
        return False


def run_once(store, config, *, start=None, end=None) -> dict:
    end = end or datetime.now(UTC)
    start = start or end - timedelta(seconds=config.lookback_seconds)
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Scan timestamps must include a timezone and start must precede end")
    started = monotonic()
    events = store.read_authentication(start - timedelta(seconds=config.window_seconds), end, config.max_events)
    findings = evaluate(events, start, end, config)
    store.write_findings(findings)
    return {
        "scan_start": start.isoformat(), "scan_end": end.isoformat(),
        "events_read": len(events), "events_eligible": sum(event.eligible for event in events),
        "findings_matched": len(findings), "seconds": round(monotonic() - started, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--since", type=datetime.fromisoformat)
    parser.add_argument("--until", type=datetime.fromisoformat)
    args = parser.parse_args()
    if (args.since or args.until) and not args.once:
        parser.error("--since and --until require --once")
    logging.basicConfig(level=logging.INFO)
    config = DetectionSettings.from_env()
    if args.healthcheck:
        raise SystemExit(0 if healthy(config) else 1)
    store = DetectionStore(replace(settings, trino_user="ulpf_detector"))
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    initialized = False
    while not stopped.is_set():
        delay = config.interval_seconds
        try:
            if not initialized:
                store.ensure_storage()
                initialized = True
            result = run_once(store, config, start=args.since, end=args.until)
            if not args.once:
                HEARTBEAT.write_text(str(time()))
            print(json.dumps(result), flush=True)
        except Exception:
            if args.once:
                raise
            LOGGER.exception("Detection scan failed; the next poll will rescan the configured lookback")
            delay = min(30, config.interval_seconds)
        if args.once:
            return
        stopped.wait(delay)


if __name__ == "__main__":
    main()
