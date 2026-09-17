# Export diagnosis before changes — September 17, 2026

Baseline commit: `b9097dc`. All eight original inputs were rerun through the official OCSF 1.8.0 event validator before any fix. Three passed (Syslog Network Activity 4001/4, Log4j Application Error 6008/6, XML API Activity 6003/6); five failed. No warnings were returned.

The exact source log lines are retained, without modification, in [cases.json](../tests/fixtures/ocsf-1.8.0/cases.json). The corresponding pre-fix outputs are available at baseline commit `b9097dc` in `tests/fixtures/ocsf-1.8.0/expected/`.

| Input case | Class/category | Exact validator rule and message |
| --- | --- | --- |
| `cef-finding` | 2004/2 | `attribute_unknown`: Unknown attribute at "src_endpoint"; attribute "src_endpoint" is not defined in class "detection_finding" uid 2004. |
| `leef-finding` | 2004/2 | `attribute_unknown`: Unknown attribute at "src_endpoint"; attribute "src_endpoint" is not defined in class "detection_finding" uid 2004. |
| `json-authentication` | 3002/3 | `attribute_required_missing`: Required attribute "user" is missing. `constraint_failed`: Constraint failed: "at_least_one" from class "authentication" uid 3002; expected at least one constraint attribute, but got none. Constraint attributes: `service`, `dst_endpoint`. |
| `apache-http` | 4002/4 | `attribute_unknown`: Unknown attribute at "actor"; attribute "actor" is not defined in class "http_activity" uid 4002. `constraint_failed`: Constraint failed: "at_least_one" from class "http_activity" uid 4002; expected at least one constraint attribute, but got none. Constraint attributes: `http_request`, `http_response`. |
| `csv-api` | 6003/6 | `attribute_required_missing`: Required attribute "src_endpoint" is missing. |

## Root-cause clusters

1. **Shared, class-insensitive export:** the exporter adds endpoints and actor before considering class. CEF and LEEF therefore produce the same invalid finding shape. This is not two parser bugs.
2. **Authentication projection:** the parsed subject is exported only as `actor.user`, while Authentication requires a target `user`; the parsed service is not projected to `service`. This is another class-specific exporter omission, not incorrect class/category or type IDs.
3. **HTTP projection:** the parser retains status/path/protocol but the exporter never constructs a request or response. The generic actor emission is also invalid for HTTP Activity.
4. **Incomplete API evidence:** the CSV input genuinely has no source address. There is nothing truthful to project to the required endpoint. A policy for incomplete API events is needed; adding a made-up address or an empty endpoint merely to pass validation is not acceptable.

Fixes must preserve flattened storage fields and retained source evidence. Changing interchange shape does not migrate previously persisted JSON. The original eight inputs must remain unchanged so a rising pass count measures actual fixes, not easier examples.
