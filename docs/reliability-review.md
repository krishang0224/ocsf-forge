# Reliability review follow-up — September 17, 2026

## 1. Diagnose before fixing

All original inputs were validated before code changes: 3/8 passed. [Diagnosis](validation-diagnosis.md) records class/category, exact errors and source-input links, committed separately in `8ef642b`.

## 2. Cluster root causes

CEF and LEEF shared a class-insensitive export bug. Authentication and HTTP needed distinct projections of already parsed evidence. CSV lacked required evidence entirely. No class/category or computed type-ID mismatch caused these five failures.

## 3. Fix in leverage order

- Finding context: `64ab583`, followed by compatibility correction in `f107268`. Endpoints/actor are invalid at the finding root, so retain them under `unmapped.normalized_context`. Existing rule metadata paths remain unchanged unless a vendor key collides. New parameterized `test_findings_retain_endpoints_and_user_without_forbidden_root_attributes` covers CEF/LEEF, both endpoints, user and collisions.
- Authentication: `f107268`. The generic actor was not the required target user, and the explicit service was discarded during projection. Retain that source service and export `user`/`service`; do not infer it from a default product. New tests cover both populated and absent fields. Parser versions were bumped; existing persisted JSON is not rewritten.
- HTTP: `1eac9c4`. Status/body size were parsed but remained only unmapped; generic actor was forbidden. Export observed `http_response` and preserve the rest without inventing an absolute request URL. New test covers known/unknown sizes and retained logged user/request path.
- Full eight-fixture official runs after fixes yielded 5/8, 6/8 and 7/8. One network-interrupted run was retried in full. Local full-suite testing caught and corrected the rule-metadata compatibility regression before proceeding.
- Deferred: the original CSV source has no endpoint. Test `test_incomplete_api_fixture_remains_a_visible_failure_without_invented_endpoint` keeps it a negative case. A cross-cutting strict-export/quarantine policy is not silently introduced. See [issue #11](https://github.com/krishang0224/ocsf-forge/issues/11).

## 4. Track distinct causes

[Finding #8](https://github.com/krishang0224/ocsf-forge/issues/8), [Authentication #9](https://github.com/krishang0224/ocsf-forge/issues/9) and [HTTP #10](https://github.com/krishang0224/ocsf-forge/issues/10) are closed with fixing commits and regression-test references. Missing API evidence #11 remains open.

## 5. Reconcile claims

README and the OCSF guide explicitly say **7/8**, not fully conformant. The worked Syslog example was already a passing baseline case; its adjacent text disclosed the then-lower overall pass count. No original input was replaced to inflate results. [Current validation report](ocsf-validation.md) separates historical results, fixes and remaining limits.

## 6. Evidence integrity

SHA-256 computation/storage already existed; the gap was visibility. Current data and Batch preview now show the existing digest. The UI integration test requires both views to contain it, and the ingestion test verifies the digest. A hash is neither source authentication nor protection against replacing both payload and hash. Structured records are logical payloads, not necessarily original whole-file bytes. [Threat model](evidence-integrity.md).

## 7. Stuck runs

No scheduled inspection existed. The maintenance process now emits a bounded stale-run report with configurable timeout and polling. Flag-only is deliberate: elapsed time does not prove the writer died, and run metadata is not a complete replay source. Tests cover query parameters/filtering, output bounds, failure propagation, invalid settings and separate compaction timing. A live Trino watchdog check remains unperformed; long maintenance work can delay polling. [Operations](operations.md#stale-run-watchdog).

## 8. Packaging

The package already had `__version__`, but no build/project metadata. The wheel now derives its version from that source, exposes `ocsf-forge`, and reuses pinned files for backend extras. The core has no runtime dependencies. A wheel was built and installed in a fresh environment outside the checkout; the CLI demo and installed-version comparison passed. CI repeats this smoke test. Dashboard deployment files remain in the checkout; no PyPI release was published.

## 9. Exception redaction

Several UI paths displayed raw backend exceptions. Shared handling now logs the complete exception with a short ID and displays only a generic message/reference. Explicit `ULPF_DEBUG_ERRORS=true` restores trusted-local debug details. Tests check secret exclusion, server correlation, opt-in details and a real Streamlit ingestion failure. Server logs must themselves be protected; this is not general authentication or log sanitization.

## 10. Coverage

CI reports `ulpf` statement/branch coverage and missing lines. Local result: **258 passed, 2 skipped; 78% combined statement/branch coverage**. This measurement excludes code executed only in separate subprocesses and live services; it is not a security or conformance guarantee. No artificial threshold or static README coverage badge was added.

## 11. Compose claims

Operations documentation distinguishes prior Podman end-to-end recovery tests from Docker Compose configuration checks. No minimum-version matrix or fresh-stack run is claimed. All-profile configuration validation and lint passed for this change set. No local services were started.
