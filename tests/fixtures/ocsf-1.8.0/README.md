# OCSF 1.8.0 fixtures

`cases.json` contains synthetic inputs, filenames and expected class contracts. `expected/` contains actual exporter output, including its current defects. These files are regression snapshots, not corrected reference events.

`validation.fixtures.export` runs each input through the real pipeline with `fixture:<case-name>` as source identity. Each source carries an explicit timestamp; only collection time is fixed to `2026-09-01T00:01:00+00:00`. CLI exports can have different IDs and collection times because they use different source identity and observation time.

`contracts/` contains resolved class definitions retrieved from the official version-pinned API, not JSON Schema files. `provenance.json` records URLs, file hashes and the upstream 1.8.0 tag commit. See `UPSTREAM-NOTICE` for attribution. The checker verifies those hashes before using the snapshots.

`known-gaps.json` records the deliberately failing partial-check baseline. Do not erase errors merely to make CI green. First correct and test the mapping, then review changed snapshots and document compatibility consequences.

See the [audit results and reproduction commands](../../../docs/ocsf-validation.md). Full schema conformance is not established.

The independent official toolkit gate validates fresh pipeline exports using [pinned upstream artifacts](../../../validation/toolchain-lock.json). Its [per-fixture expectations](../../../validation/expected-results.json) require no findings for the seven positives and only the missing `src_endpoint` error for CSV. It does not use the expected-output snapshots to decide schema validity.
