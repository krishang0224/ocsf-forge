# Changelog

Changes to parser output, event identity, and storage layout are recorded here. No versioned release has been published yet; commit links identify the existing baseline.

## Unreleased

- Add Apache-2.0 licensing, CI checks, contribution guidance, and an explanation of the OCSF mapping.
- Add screenshots of the dashboard, SQL workspace, and ingestion results using bundled sample data.
- Replace the fixed README test count with a link to CI and remove the five-minute setup promise.
- No application behavior or Iceberg table layout changes in this documentation update.

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
