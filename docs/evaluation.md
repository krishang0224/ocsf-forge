# Evaluating OCSF Forge

Start with `python -m ulpf demo` from the repository root using Python 3.11. No third-party packages or services are required. Stdout contains three OCSF-aligned findings; stderr reports 15 synthetic input events. Inspect `unmapped.rule_id`, `unmapped.evidence_event_ids`, and `metadata.uid` to trace the result.

Next, run `python -m ulpf normalize your-logs.jsonl > normalized.jsonl`. Inspect stderr and the exit status before using the output: rejected events are not included in stdout. Keep the input file because this offline command does not store quarantine. Use the full lakehouse when durable raw/quarantine tables and SQL are required.

## What to verify

- Normalize a representative sample from the intended source. Generic JSON/XML support is not a substitute for vendor-specific field mapping.
- Check timestamps, user identity, hostname, service, outcome, and network fields—not only the parse-success count.
- For detection, use explicit authentication outcomes. Missing outcomes must not be inferred as success. A failed authentication pattern is an investigation lead, not proof of compromise.
- Replay the same source and offsets against the lakehouse, and verify uniqueness by event ID.
- Open a finding and load its supporting events. Investigate missing evidence before drawing conclusions.
- Test restart/recovery and retention against non-production data before deployment.

## Audit checkpoint: 2026-09-08

This is a dated development checkpoint, not a continuously updated certification. The current automated status is in GitHub Actions.

- 159 offline tests passed, including a seeded corpus of 1,000 malformed structured records, CLI subprocess tests, JSON/CSV rejection cases, and SQL evidence binding.
- The CLI demo passed with Python site packages disabled.
- The live detection integration test passed separately: ingestion, all three findings, duplicate-safe replay, and permission denials.
- The catalog initializer restarted successfully against existing persistent state. All core containers reported healthy.
- A browser check loaded supporting normalized events from the Findings tab.
- Lint, dependency consistency, and all-profile Compose configuration checks passed.
- Local services were stopped after validation; persistent data was retained.

The catalog bootstrap now serializes credentials, rejects unexpected conflicts, and tests Lakekeeper's nested error response. A clean-volume first boot with non-default credentials was not repeated in this checkpoint. Live Kafka load and production authentication/TLS were also not exercised here.

## Adoption gates still ahead

Before advertising production readiness, establish full OCSF schema-conformance tests, representative vendor fixtures with documented mappings, authenticated deployment tests, fresh-volume integration CI, and recovery tests covering broker/storage failures. Publish versioned releases and a repeatable hardware-labelled benchmark harness before treating throughput results as a capacity-planning guide.

These are stronger evidence for adoption than adding more rule names without fixtures or claiming support for every log format.
