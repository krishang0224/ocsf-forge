# Authentication detections

The optional detection worker reads authentication logons from `iceberg.logging.application_logs` and writes local OCSF class-2004 findings to `iceberg.logging.detections`. It does not modify source records or take automated response actions. CEF and LEEF alerts received from other products remain in `application_logs`; the Findings tab shows locally generated findings.

## Rules

All rules use a sliding five-minute window by default. The scope is the exact hostname, service name, and source IP; user-specific rules also require the same username.

| Rule | Trigger | Common benign explanations |
| --- | --- | --- |
| `auth.repeated_failures` | At least 5 failed logons for one user | Stale credentials, repeated typing errors |
| `auth.password_spray` | Failed logons for at least 5 distinct users | Shared NAT addresses, authentication testing |
| `auth.success_after_failures` | A successful logon preceded by at least 5 failures for the same user and source IP | A legitimate user finally enters the correct password |

These are High-severity investigation leads, not proof of compromise. They do not detect distributed attacks across source IPs, slow attempts outside the window, or activity absent from the normalized logs. Host and service names must identify the same authentication domain consistently; isolate tenants that reuse those names.

Inputs must have `class_uid=3002`, `activity_id=1` (Logon), `status_id=1` (Success) or `2` (Failure), and nonempty event ID, hostname, service, source IP, and username. Missing identities are skipped and reported through the difference between `events_read` and `events_eligible`. The generic JSON/CSV/XML mapping recognizes actions such as `login_failure` and `login_success`; arbitrary vendor status fields may require a dedicated parser. Existing generic Syslog records are not automatically SSH authentication records.

## Run and try it

```bash
docker compose --profile detection up --build -d
docker compose exec -T app python -m ulpf.detection.demo > /tmp/ocsf-detection-demo.jsonl
```

Open the app, upload `/tmp/ocsf-detection-demo.jsonl`, and click **Ingest into Iceberg**. The file contains 15 synthetic logons: a repeated-failure sequence followed by success, a spray sequence, and four failures below the threshold. Within a polling interval, open **Findings** and click **Refresh findings**. With default thresholds, the demo produces three findings. Repeating the generator at a later time can create new findings; replaying the same file is deduplicated.

```bash
docker compose --profile detection logs -f detection-worker
```

Successful scans log the range, rows read, eligible rows, matched findings, and duration. `findings_matched` includes matches already stored; it is not a count of newly inserted rows. Container health requires a recent successful scan. An empty Findings tab alone does not prove the worker is running.

## Timing, replay, and limits

The worker scans the preceding hour every 30 seconds and reads an extra rule window before the scan start for context. Correlation uses normalized event time, including collector time when the parser explicitly allows it. Events exactly at the range end are considered by a later poll. A success must be strictly later than its failures; equal timestamps do not establish order.

Each finding ID hashes the rule ID/version, threshold, window length, scope, subject, and a UTC window-sized suppression bucket. Sliding windows can cross bucket boundaries; suppression buckets only limit repeated alerts. There is at most one finding per rule and subject in each bucket. Stored findings retain the first matching evidence; later scans do not update them. Changing thresholds or rule versions can intentionally create new IDs.

Writes use parameterized, size-limited Iceberg MERGE statements. Failed or partially completed writes can be replayed. Run one detection worker per deployment: this version has no distributed lock or checkpoint. Late arrivals within the lookback are reconsidered; older arrivals, long outages, and historical uploads require an explicit backfill. Scan length and row limits also bound this worker's memory and detection coverage.

For a historical scan, stop the polling worker first, then run a one-off container:

```bash
docker compose --profile detection stop detection-worker
docker compose --profile detection run --rm --no-deps detection-worker \
  python -m ulpf.detection.worker --once \
  --since 2026-09-07T00:00:00+00:00 --until 2026-09-08T00:00:00+00:00
docker compose --profile detection start detection-worker
```

Use your actual event range and include timezone offsets. A scan exceeding the row cap fails before writing findings; it never evaluates a truncated input batch. Split large backfills into smaller ranges, or raise the cap if memory permits. Each range automatically includes preceding context.

## Configuration

Settings are environment variables exposed in `.env.example` and Compose.

| Variable | Default | Meaning |
| --- | ---: | --- |
| `ULPF_DETECTION_WINDOW_SECONDS` | 300 | Correlation window and suppression bucket width |
| `ULPF_DETECTION_FAILURE_THRESHOLD` | 5 | Failures for repeated-failure and subsequent-success rules |
| `ULPF_DETECTION_SPRAY_THRESHOLD` | 5 | Distinct users with failed logons |
| `ULPF_DETECTION_LOOKBACK_SECONDS` | 3600 | Event-time range rescanned on each poll |
| `ULPF_DETECTION_INTERVAL_SECONDS` | 30 | Pause between scans |
| `ULPF_DETECTION_MAX_EVENTS` | 50000 | Maximum input rows, including preceding context |
| `ULPF_DETECTION_EVIDENCE_LIMIT` | 20 | Maximum event IDs retained in each finding |

Evidence is sampled when necessary; `unmapped.evidence_truncated` makes that explicit. Spray findings also include `unmapped.distinct_user_count`. Query source records by `application_logs.event_id` using the IDs in `evidence_event_ids_json`, or inspect/download the OCSF document in the Findings tab. `first_seen` and `last_seen` describe the matching evidence; `detected_at` records when the finding was created.

## Storage and permissions

The migration only adds `detections`. App initialization and worker initialization create it if missing. The detector identity `ulpf_detector` can read `application_logs` and manage its finding table; table rules deny raw/quarantine reads and source-table writes. The reader and dashboard can read findings. The bundled stack still needs real authentication before these identities are a production security boundary; see [production security](production-security.md).

Compaction and retention support `detections`; add it to an existing `ULPF_MAINTENANCE_TABLES` override when upgrading. To roll back, stop the detection worker and run the previous application version. Retain the additive table for investigation; no source-table rollback is needed. There is no finding lifecycle UI, notification delivery, or automatic remediation in this version.

## Verification

Offline rules and storage tests run with the normal test suite. The optional integration test ingests a uniquely identified synthetic batch, checks all rules and replay behavior, verifies table permissions, and removes its test rows afterward. Start the core stack and stop the polling detector before running it:

```bash
ULPF_RUN_LIVE_TESTS=1 pytest -q tests/test_detection_live.py
```

The export follows the project's [OCSF 1.8 mapping](why-ocsf.md) and uses the existing [Detection Finding class](https://github.com/ocsf/ocsf-schema/blob/1.8.0/events/findings/detection_finding.json). It is not a claim of complete OCSF schema certification.
