# OCSF export validation

The target is OCSF 1.8.0, but the current exporter is **not fully conformant**. Passing parser tests establishes neither schema conformance nor correct vendor semantics.

## Current result

5/8 original fixtures pass after the finding projection correction. Authentication, HTTP and incomplete CSV API evidence remain unresolved. See [pre-fix diagnosis](validation-diagnosis.md).

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

These are findings about these exact examples, not pass rates for production data or guarantees about every event of a format. The CSV source lacks an address; inventing one just to satisfy a schema is not a valid fix. Other failures require class-specific export mappings. Runtime mappings and persisted data have not been changed by this audit.

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

CI runs the **known-gap regression baseline**, not a conformance certification. Fixing a mapping must update the expected output and documented gaps deliberately, with compatibility tests and a changelog entry.

## Scope and provenance

[Fixtures](../tests/fixtures/ocsf-1.8.0/README.md) cover all six currently supported classes and eight formats. Inputs, complete expected exports, upstream source URLs, SHA-256 digests, and the upstream tag commit are committed together.

The offline checker consumes resolved class definitions from the official API. Those definitions are **not JSON Schema**. It checks top-level required/unknown attributes, basic types, enums, class constraints, derived type IDs and the declared version. It does not recursively validate nested objects, profiles, extensions, observables, patterns or vendor meaning. The upstream JSON Schema export endpoint timed out during this audit, so no local full-JSON-Schema validation is claimed; the separate live check uses the official event validator instead.

A schema-valid event can still describe the wrong action. Vendor-specific mapping tests remain necessary even after these structural failures are corrected.
