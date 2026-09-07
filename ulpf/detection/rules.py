"""Sliding-window authentication rules with deterministic finding identities."""

import hashlib
import json
from collections import Counter, defaultdict, deque
from datetime import UTC, datetime, timedelta
from itertools import islice

from ulpf.detection.config import DetectionSettings
from ulpf.detection.models import AuthenticationEvent, Detection
from ulpf.models import NormalizedEvent

RULE_VERSION = "1.0.0"
RULE_TITLES = {
    "auth.repeated_failures": "Repeated login failures",
    "auth.password_spray": "Possible password spraying",
    "auth.success_after_failures": "Successful login after repeated failures",
}


def evaluate(
    events: list[AuthenticationEvent],
    start: datetime,
    end: datetime,
    config: DetectionSettings | None = None,
    *,
    detected_at: datetime | None = None,
) -> list[Detection]:
    config = config or DetectionSettings()
    if any(value.tzinfo is None for value in (start, end)) or start >= end:
        raise ValueError("Detection range must be timezone-aware with start before end")
    if len(events) > config.max_events:
        raise ValueError("Detection input exceeds max_events; reduce the scan range")
    observed = detected_at or datetime.now(UTC)
    window = timedelta(seconds=config.window_seconds)
    unique = {event.event_id: event for event in events if event.eligible}
    ordered = sorted(unique.values(), key=lambda event: (event.timestamp, event.event_id))
    pairs = defaultdict(deque)
    pair_times = defaultdict(Counter)
    sources = defaultdict(deque)
    users = defaultdict(Counter)
    findings = {}

    def emit(rule_id, trigger, evidence, count, threshold, subject):
        bucket = int(trigger.timestamp.timestamp()) // config.window_seconds
        identity = [rule_id, RULE_VERSION, config.window_seconds, threshold, *trigger.scope, subject, bucket]
        finding_id = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
        if finding_id in findings:
            return
        distinct_count = None
        if rule_id == "auth.password_spray":
            representatives = {}
            for item in evidence:
                representatives.setdefault(item.user, item)
            distinct_count = len(representatives)
            sample = list(islice(representatives.values(), config.evidence_limit - 1))
        else:
            sample = list(islice(evidence, min(config.evidence_limit - 1, count - (trigger.status_id == 1))))
        if trigger not in sample:
            sample.append(trigger)
        evidence_ids = tuple(event.event_id for event in sample)
        title = RULE_TITLES[rule_id]
        metadata = {
            "rule_id": rule_id,
            "rule_version": RULE_VERSION,
            "window_seconds": config.window_seconds,
            "threshold": threshold,
            "event_count": count,
            "evidence_event_ids": evidence_ids,
            "evidence_truncated": count > len(evidence_ids),
            "hostname": trigger.hostname,
            "service": trigger.service,
        }
        if distinct_count is not None:
            metadata["distinct_user_count"] = distinct_count
        event = NormalizedEvent(
            event_id=finding_id, timestamp=trigger.timestamp.astimezone(UTC).isoformat(), observed_at=observed.isoformat(),
            timezone_offset=0, category_uid=2, class_uid=2004, activity_id=1, type_uid=200401,
            category="Findings", class_name="Detection Finding", activity_name="Create",
            severity="High", severity_id=4, status="New", status_id=1,
            src_endpoint_ip=trigger.ip_address, user=subject, hostname=trigger.hostname,
            device_vendor="OCSF Forge", device_product="Authentication rules", parser_name=rule_id,
            parser_version=RULE_VERSION, source_format="detection", message=title,
            metadata=metadata,
        )
        findings[finding_id] = Detection(
            event, rule_id, RULE_VERSION, evidence[0].timestamp, trigger.timestamp, count, evidence_ids,
        )

    for event in ordered:
        if event.timestamp < start - window or event.timestamp >= end:
            continue
        pair = (*event.scope, event.user)
        previous = pairs[pair]
        times = pair_times[pair]
        source = sources[event.scope]
        distinct = users[event.scope]
        cutoff = event.timestamp - window
        while previous and previous[0].timestamp < cutoff:
            old = previous.popleft()
            times[old.timestamp] -= 1
            if times[old.timestamp] == 0:
                del times[old.timestamp]
        while source and source[0].timestamp < cutoff:
            old = source.popleft()
            distinct[old.user] -= 1
            if distinct[old.user] == 0:
                del distinct[old.user]
        if event.status_id == 2:
            previous.append(event)
            times[event.timestamp] += 1
            source.append(event)
            distinct[event.user] += 1
            if event.timestamp < start:
                continue
            if len(previous) >= config.failure_threshold:
                emit("auth.repeated_failures", event, previous, len(previous), config.failure_threshold, event.user)
            if len(distinct) >= config.spray_threshold:
                emit("auth.password_spray", event, source, len(source), config.spray_threshold, "")
        elif event.timestamp >= start:
            earlier_count = len(previous) - times[event.timestamp]
            if earlier_count >= config.failure_threshold:
                emit("auth.success_after_failures", event, previous, earlier_count + 1, config.failure_threshold, event.user)
    return list(findings.values())
