# Configuration entry points

There are three execution paths, not one interchangeable configuration surface. The offline CLI uses command-line options; the dashboard and workers read environment variables at process startup; Compose passes only the variables declared for each service.

| Area | Source of defaults and operating guidance |
| --- | --- |
| Offline CLI | `python -m ulpf normalize --help`; `--max-bytes` defaults to 25 MiB and `--max-events` to 50,000 |
| Full-stack local deployment | [`.env.example`](../.env.example), then the service-specific `environment` blocks in [Compose](../docker-compose.yml) |
| Trino connection, identities, query and ingestion limits | [`Settings`](../ulpf/config.py), [ingestion tuning](operations.md#ingestion-tuning) and [security prerequisites](production-security.md) |
| DuckDB selection, directory, memory, threads and timeout | [Homelab resource controls](homelab-mode.md#resource-controls) |
| Kafka broker/topic, group and polling | [Worker settings](../ulpf/streaming/worker.py) and the `stream-worker` Compose service |
| Detection window, thresholds, lookback and evidence | [Detection settings](detection.md) and [`DetectionSettings`](../ulpf/detection/config.py) |
| Compaction thresholds and retention | [Operations](operations.md#maintenance), [maintenance worker](../ulpf/maintenance.py) and the `maintenance` Compose service |

Compose reads `.env` for substitution. Running Python or Streamlit directly does not automatically load it. Set shell environment variables or use a service manager, then restart the process. Never commit an actual `.env` containing credentials.

`ULPF_BACKEND=duckdb` selects only the local dashboard route. It does not convert the Kafka, detection or maintenance workers to local-storage workers. A failed Trino connection never triggers a fallback. See the homelab guide before trying to reuse full-stack settings there.

The live stack and recovery tests documented in the [stress audit](stress-testing.md) used Podman Compose. CI also validates all profiles with Docker Compose. A minimum compatible Compose version has not been established by a version matrix; configuration validation alone is not an end-to-end compatibility test. The stack depends on service-health dependencies, named volumes and network aliases.
