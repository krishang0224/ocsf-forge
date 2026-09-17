# Changelog

Changes to parser output, event identity, and storage layout are recorded here. No versioned release has been published yet; commit links identify the existing baseline.

## Unreleased

- Add an independent offline official OCSF Toolkit CI gate against checksum-pinned toolkit/compiler/schema artifacts. Enforce each fixture's exact outcome and distinguish regressions from infrastructure failures; hosted validation is no longer the only recursive check.
- Add nested-field negative controls, wrong-reason/extra-error checks for the known-negative fixture, and 32 security/text parser edge-case tests. No runtime parser behavior or fixture source inputs changed.

- Display stored SHA-256 digests in Current data and Batch preview without adding duplicate hash computation. Document the digest's limited threat model.
- Add a flag-only stale-run watchdog to maintenance with independent polling and timeout settings; preserve run rows and avoid unsafe automatic replay.
- Package the dependency-free CLI with optional pinned homelab/lakehouse dependencies, reusing the existing version source. Test installation outside the checkout in CI.
- Log UI exceptions server-side with reference IDs. Raw exception details require explicit `ULPF_DEBUG_ERRORS=true`; default behavior covers ingestion, queries, findings and dashboard loading.
- Report statement/branch coverage in CI and distinguish prior Podman end-to-end testing from Docker Compose configuration validation.

- Fix #10: HTTP exports the observed response code/body length and retains logged user context outside forbidden root `actor`. Regression: `test_http_exports_response_and_preserves_request_and_authenticated_user`, including unknown response size. Official original-fixture result: 7/8; missing API endpoint evidence is explicitly deferred in #11.

- Fix #9: project Authentication subjects to `user` and retain explicitly supplied services for export. Do not infer missing services from product defaults. JSON/CSV/XML parser versions become 2.2.2/1.1.1/1.2.1. Regression: `test_authentication_exports_target_user_and_explicit_service`; missing-evidence test prevents fabrication.
- Preserve existing finding rule metadata paths when adding normalized context; only wrap source metadata if its own `normalized_context` key would collide. Full detection/CLI tests cover this compatibility boundary.

- Fix #8: Detection Finding no longer emits forbidden root endpoints/actor. Preserve those fields under `unmapped.normalized_context` with original vendor metadata under `source_fields`. Flattened storage is unchanged; previously saved JSON is not rewritten. Regression: `test_findings_retain_endpoints_and_user_without_forbidden_root_attributes`.

- Publish version-pinned OCSF fixtures and an opt-in official validator check. Document five failing synthetic exports without changing mappings or claiming conformance; CI checks the known-gap regression baseline.
- Add a worked Syslog example, documentation index, configuration entry points and evidence-hash verification limits.

- Add explicit DuckDB homelab mode with isolated dependencies, atomic local ingestion, and a read-only SQL workspace; the Trino deployment remains the default.
- Bind local ingestion by column to reduce SQL planning overhead. Add repeatable stress harnesses, real engine-memory and process-crash recovery tests, and a [dated audit](docs/stress-testing.md) including capacity failures.
- Reject unpaired Unicode JSON escapes into quarantine, including safe diagnostics for malformed keys. JSON parser version is now `2.2.1`.
- Avoid quadratic scanning and ambiguous escape backtracking in Syslog fields; preserve a quoted value's escaped final quote. Syslog parser version is now `2.1.1`. Existing persisted rows are not rewritten.
- Bound UI and offline CLI inputs to 50,000 events before normalization, in addition to the existing byte limits. Add `ULPF_MAX_UPLOAD_EVENTS` and CLI `--max-events`; direct pipeline callers remain uncapped unless they supply `max_events`.
- Keep SQL results visible when downloading and use the correct backend name in the CSV filename.

- Refresh README dashboard, SQL, ingestion, and findings screenshots for the Terminal theme. Add an Appearance preview and clarify the capture date and historical synthetic-data context.

- Replace the decorative default theme with compact Terminal styling. Add three alternative presets and a collapsed Custom appearance panel with validated, shareable URL settings. See [appearance controls and limitations](docs/appearance.md).

- Add an offline `python -m ulpf demo` and bounded `normalize` CLI with machine-readable output, rejection diagnostics, and documented exit codes.
- Reject duplicate/non-finite JSON values and malformed CSV documents; retain invalid UTF-8 bytes in quarantine metadata. Reject boolean and fractional ports, normalize naive observation times consistently, and keep record hashes consistent with stored payloads.
- Export event IDs in OCSF metadata and let investigators load a finding's supporting normalized records directly.
- Validate unsafe or nonsensical connection/batching settings at startup. Correct atomicity and format-coverage claims and document whole-file evidence preservation limits.
- Serialize catalog credentials as JSON rather than shell-interpolated strings. Catalog initialization now rejects unexpected conflicts instead of treating every HTTP 409 as success.

- Preserve pasted Syslog records, BOM-prefixed JSON, hostname-valued servers, and malformed records without aborting the batch. Authentication outcomes must be explicit; ambiguous login events no longer imply success, and conflicting outcomes are quarantined.
- Decode JSON once and assemble multiline traces with a single join. Bound ingestion previews and defer full-batch exports until requested.
- Close Trino cursors after limited queries, recognize quoted SQL correctly, and select audit snapshots by commit time instead of snapshot ID.
- Quarantine Kafka tombstones, empty messages, and invalid UTF-8; preserve invalid bytes in base64 metadata. Require successful dead-letter acknowledgments before committing offsets.
- These parser changes affect new ingestion only. Existing rows and findings are not rewritten by replay; review historical authentication findings before relying on them.

- Add an optional authentication detection worker, an additive `detections` table, a Findings view, and a synthetic demo. See [detection operations](docs/detection.md) for thresholds, backfills, and rollback.
- Restrict the detector's table permissions to reading normalized events and managing findings; allow analysts to read findings.

## 2026-09-06 — Repository documentation

- Add Apache-2.0 licensing, CI checks, contribution guidance, and an explanation of the OCSF mapping.
- Add screenshots of the dashboard, SQL workspace, and ingestion results using bundled sample data.
- Replace the fixed README test count with a link to CI and remove the five-minute setup promise.
- No application behavior or Iceberg table layout changes in that documentation update.

## 2026-09-05 — Structured ingestion and recovery

[Commit c5561bc](https://github.com/krishang0224/ocsf-forge/commit/c5561bc)

- Route pasted CSV, XML, and multiline JSON through the upload parsing path.
- Preserve repeated XML fields and escaped LEEF delimiters; restrict stack-trace continuation to Log4j.
- Reject unsupported OCSF classes and deduplicate event IDs within an ingestion batch.
- Retry streaming storage initialization and writes; require a catalog query for Trino readiness.
- Existing stored rows are not rewritten. Replaying identical source IDs and offsets deduplicates completed rows; it does not update their previous parser output.

## Earlier development baseline

[Lakehouse implementation](https://github.com/krishang0224/ocsf-forge/commit/83f8219), [load hardening](https://github.com/krishang0224/ocsf-forge/commit/598b8bf), and [project rename](https://github.com/krishang0224/ocsf-forge/commit/51ed03b).

- Introduce raw, normalized, quarantine, and ingestion-run tables with deterministic event IDs and recoverable writes.
- Add size-aware batching and retries for concurrent Iceberg commit conflicts.
- Rename the public project to OCSF Forge while retaining the `ulpf` package and configuration names.

These commits predate this changelog. Consult their diffs before upgrading an older checkout; see [operations and recovery](docs/operations.md) for backup and replay behavior.
