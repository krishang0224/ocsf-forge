# Why OCSF?

Logs can describe the same login failure using different names for the user, source address, action, and severity. A private schema would unify those names inside this project, but every downstream consumer would then need to learn that private model.

The [Open Cybersecurity Schema Framework](https://github.com/ocsf/ocsf-schema) provides shared event classes, attributes, and identifiers for security data. OCSF Forge maps supported inputs to that vocabulary so a query can group authentication failures across formats using the same class and status fields. The mapping is deterministic and can be tested against fixed fixtures.

## What this project maps

The current target is [OCSF 1.8.0](https://github.com/ocsf/ocsf-schema/tree/1.8.0). The normalizer checks supported class/category pairs, derives type IDs from class and activity, and validates severity, timestamps, addresses, and ports. The OCSF export uses nested endpoint and actor fields; the Iceberg table also exposes flattened columns for SQL.

Original payloads remain in `raw_events`. Unmapped vendor fields are retained as metadata, and invalid records enter quarantine with a reason. A shared schema should not require discarding source evidence.

## Limits and tradeoffs

OCSF does not tell a generic parser what every vendor field means. A JSON object with an ambiguous action still needs a source-specific mapping before its security meaning can be trusted. The bundled parsers cover a subset of OCSF classes; these checks are not complete validation against every OCSF schema constraint or a certification of compliance.

Adding a class requires an explicit category mapping and tests. Changing a mapping can affect saved queries and reprocessing, so parser versions and schema changes need to be recorded in the changelog. See [parser development](parser-development.md) and [operations](operations.md).

OCSF handles the event vocabulary. Iceberg handles durable tables and snapshots, Trino handles SQL, and Kafka handles transport. Each can evolve independently, but changing the event contract still needs a migration plan.
