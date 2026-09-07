# Security policy

Report suspected vulnerabilities privately through [GitHub private vulnerability reporting](https://github.com/krishang0224/ocsf-forge/security/advisories/new).

Do not publish undisclosed vulnerabilities, exploit details, credentials, or private logs in public issues or pull requests.

Include the affected commit, deployment configuration, reproduction steps, expected security boundary, and potential impact. Use synthetic or redacted inputs. Ingestion, parser handling, SQL permissions, and infrastructure configuration are all relevant.

Security fixes target the latest `main` branch. There are no maintained release branches or guaranteed backports yet.

The maintainer will use the private report to discuss reproduction, remediation, and disclosure. This project does not offer a guaranteed response time or a paid bug bounty.

For deployment precautions, see the [production security checklist](../docs/production-security.md). Ordinary bugs belong in the [bug report form](https://github.com/krishang0224/ocsf-forge/issues/new?template=bug_report.yml).
