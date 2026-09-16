# Documentation

Start with the [repository overview and quickstarts](../README.md). Choose the offline CLI for evaluation, DuckDB for a local dashboard, or the full lakehouse for Kafka ingestion and scheduled detections.

| Question | Guide |
| --- | --- |
| Can I evaluate this without running services? | [Evaluation and offline CLI](evaluation.md) |
| How do I run the lightweight dashboard? | [Homelab setup, resource limits and SQL differences](homelab-mode.md) |
| What does the OCSF mapping guarantee? | [Why OCSF and mapping limits](why-ocsf.md) |
| Can I independently check the exports? | [OCSF fixture audit and known failures](ocsf-validation.md) |
| How do I check the retained payload? | [Evidence hashes and their limits](evidence-integrity.md) |
| How do I add a log source? | [Parser development](parser-development.md) and [contributing](../CONTRIBUTING.md) |
| What do the authentication rules detect? | [Detection, evidence and worker operations](detection.md) |
| How do I recover or tune ingestion? | [Persistence, replay and maintenance](operations.md) |
| Where are the configuration settings? | [Configuration entry points](configuration.md) |
| What must change before network exposure? | [Production security prerequisites](production-security.md) |
| What has actually been load-tested? | [Dated stress results and reproducible harnesses](stress-testing.md) |
| Can I change the dashboard appearance? | [Themes and appearance controls](appearance.md) |

Project policies: [Apache-2.0 license](../LICENSE), [security reporting](../.github/SECURITY.md), [changelog](../CHANGELOG.md), [issue templates](../.github/ISSUE_TEMPLATE/), [full-stack CI](../.github/workflows/ci.yml), [homelab CI](../.github/workflows/homelab.yml).
