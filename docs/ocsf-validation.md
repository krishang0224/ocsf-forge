# OCSF export validation

The target is OCSF 1.8.0, but the current exporter is **not fully conformant**. Passing parser tests establishes neither schema conformance nor correct vendor semantics.

## Current result

7/8 original fixtures pass after the finding, Authentication and HTTP projection corrections. All eight were rerun after each correction. An interrupted Authentication-stage network run was retried in full, not counted as a pass. See [pre-fix diagnosis](validation-diagnosis.md).

The same 7/8 outcome is now enforced on pushes and pull requests by the **offline official OCSF Toolkit gate**. The seven named positive fixtures must have zero findings, including warnings. CSV must have exactly `error / validation_attribute_required_missing / src_endpoint` and nothing else. A green gate means the explicit positive and negative expectations hold, not that all eight events conform.

The original inputs were not changed. CEF/LEEF context is retained under `unmapped.normalized_context`; existing vendor fields stay at their previous paths unless their key collides, in which case they are wrapped under `source_fields`. Authentication exports the target `user` and explicit `service`. HTTP exports recorded response status/body length, retaining request details and user context without fabricating a full URL. Flattened storage is unchanged; old persisted interchange JSON is not migrated automatically.

### Deferred: incomplete API evidence (#11)

The CSV API fixture still fails `attribute_required_missing` for `src_endpoint`. Its input has no source address. This is an intentional, visible failure, not a corrected event: no fake IP, empty object or replacement fixture has been used to inflate the count. Quarantining all incomplete API events or adding strict-export rejection affects CLI, UI downloads, ingestion and historical records. That policy is deferred in [issue #11](https://github.com/krishang0224/ocsf-forge/issues/11). Do not use these exports in a consumer requiring full conformance until the required source evidence and export policy are supplied.

Regression tests in `tests/test_ocsf_projection.py` cover each corrected shape, metadata collisions, absent service/user fields and missing API addresses. The default partial audit still exits 1. The offline snapshot baseline and official per-fixture gate pass only when their documented expectations hold.

## Offline official gate

OCSF publishes an [event-validation CLI, ocsf-toolkit](https://github.com/ocsf/ocsf-toolkit/tree/v0.9.0). Do not confuse it with [ocsf-validator](https://github.com/ocsf/ocsf-validator), which validates contributions to the schema itself. Raw OCSF definitions are not standalone JSON Schema documents: they require resolving OCSF includes, inheritance and dictionary references. We use the [official compiler](https://github.com/ocsf/ocsf-schema-compiler/tree/865887a9ee88580c471062f93da115e7599fa31d), not an independently written schema interpreter.

[toolchain-lock.json](../validation/toolchain-lock.json) pins toolkit v0.9.0, its source commit, the compiler commit, and OCSF 1.8.0's schema commit. Download archives are checked against committed SHA-256 hashes before extraction or execution. Preparation rejects compiler diagnostics, wrong versions and unsupported output formats; a manifest detects stale or accidentally changed prepared artifacts. These checks do not protect against an attacker changing both trusted repository pins and code.

On Linux x86_64, from the repository root:

```bash
# One-time preparation needs network access and Python 3.14+ for the compiler.
python3.14 -m validation.prepare_toolkit

# Application runtime stays Python 3.11. No hosted API or services are used here.
python3.11 -m validation.check_toolkit
ULPF_OCSF_TOOLKIT_DIRECTORY=.cache/ocsf-validator python3.11 -m pytest -q tests/test_toolkit_gate.py
```

Use `--directory PATH` on both commands to choose a different artifact directory. The compiler ignores platform extensions for this base-schema fixture gate. The runtime gate validates fresh pipeline exports, not the committed `expected/` snapshots, and enables no enrichment, removal or suppressed validation checks. It compares all findings by severity, code and attribute path; duplicate or additional findings fail too. Source events are never sent outside the machine.

Gate exit codes: `0` means every per-fixture expectation matched; `1` means at least one result changed; `2` means validator infrastructure/reporting failed. Missing binaries, timeouts, malformed reports and incomplete-processing issues cannot become a validation pass. The toolkit CLI's default successful exit alone is insufficient; the adapter checks its report.

The CI `ocsf-schema-gate` job prepares the pinned artifacts, runs the gate and exercises nested negative controls: integer user names, string HTTP response codes, invalid IP strings, and an extra nested error in the known-negative CSV. An invalid IP is a toolkit warning, which our zero-findings policy still rejects. Tests also reject swapped failing fixtures and wrong failure reasons. These toolkit-dependent tests may skip in an unprepared developer environment, but CI supplies the bundle explicitly and runs them in its dedicated job.

Setup still needs GitHub downloads and the Python runtimes. A download outage fails setup; it does not mean the schema is wrong or that validation passed. Once prepared, validation is offline. The wrapper currently supports Linux x86_64 only. Eight synthetic cases and these negative controls do not certify all vendor semantics, profiles, extensions or every validator rule. Upstream pin upgrades must be reviewed; do not regenerate expected findings just to make an upgrade green.

## Independently checked baseline results

On September 17, 2026 (Asia/Kolkata), all eight bundled synthetic fixtures were submitted to the [official, version-pinned validator](https://schema.ocsf.io/1.8.0/api/v2/validate). Three passed without errors or warnings; five failed:

| Fixture | Class | Official result |
| --- | --- | --- |
| CEF finding | 2004 | Unknown top-level `src_endpoint` |
| LEEF finding | 2004 | Unknown top-level `src_endpoint` |
| JSON authentication | 3002 | Missing `user`; requires at least one of `service` or `dst_endpoint` |
| Syslog network | 4001 | No errors or warnings |
| Apache HTTP | 4002 | Unknown top-level `actor`; requires `http_request` or `http_response` |
| Log4j error | 6008 | No errors or warnings |
| CSV API | 6003 | Missing required `src_endpoint` |
| XML API | 6003 | No errors or warnings |

These baseline findings describe exact examples, not production pass rates or guarantees about every event of a format. Current corrections are recorded above; persisted data is not rewritten.

## Reproduce

From the repository root with Python 3.11:

```bash
# Offline, partial contract check: currently exits 1 because gaps exist.
python -m validation.check_ocsf

# Regression baseline: exits 0 only when exports and documented gaps match.
python -m validation.check_ocsf --check-baseline

# Opt-in network check using the official OCSF event validator.
python -m validation.check_ocsf --live
```

Exit codes: `0` means the selected check passed, `1` means validation/baseline mismatch, and `2` means a check could not complete. Live mode first verifies the upstream version and sends only bundled synthetic events, never local ingested data. Network failures must not be read as successful validation. Save its JSON-lines stdout if an audit record is needed.

CI retains the **known-gap snapshot baseline** alongside the separate official toolkit gate. Updating a snapshot cannot bypass the latter. Fixing a mapping must update the expected output and documented gaps deliberately, with compatibility tests and a changelog entry.

## Scope and provenance

[Fixtures](../tests/fixtures/ocsf-1.8.0/README.md) cover all six currently supported classes and eight formats. Inputs, complete expected exports, upstream source URLs, SHA-256 digests, and the upstream tag commit are committed together.

The older `check_ocsf` offline checker consumes resolved class definitions from the official API. Those definitions are **not JSON Schema**. It checks top-level required/unknown attributes, basic types, enums, class constraints, derived type IDs and the declared version. It does not recursively validate nested objects, profiles, extensions, observables, patterns or vendor meaning. The separate toolkit gate now provides recursive official validation; no custom full-JSON-Schema validator is claimed. The opt-in live check remains available for comparison with the hosted OCSF server, a distinct upstream implementation.

A schema-valid event can still describe the wrong action. Vendor-specific mapping tests remain necessary even after these structural failures are corrected.
