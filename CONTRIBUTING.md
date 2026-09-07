# Contributing

New parsers, regression fixtures, and reproducible bug reports are welcome.

For a new log format, start with [parser development](docs/parser-development.md). Implement and register a parser in `ulpf/parsing/`, include representative and malformed fixtures, and increment its version when output changes. New OCSF classes also need an entry in `OCSF_CLASS_CATEGORIES` in `ulpf/normalizer.py` and validation tests.

Use Python 3.11 and install `requirements-dev.txt` in a virtual environment. Before opening a pull request, run `ruff check .`, `pytest -q`, and `docker compose --profile streaming --profile operations --profile detection config --quiet`. These checks do not require a running lakehouse.

Detection rules live in `ulpf/detection/`. Include threshold, boundary, benign-activity, and replay tests when changing a rule; increment its version when its meaning changes. See [detection operations](docs/detection.md) for the optional live integration test.

Describe the input that failed, the expected result, and how you verified the change. Use synthetic or redacted logs; never include credentials or private production data.

For storage changes, document migration and rollback steps in [operations](docs/operations.md) and add an entry under Unreleased in [CHANGELOG.md](CHANGELOG.md). Call out any change to event IDs, parser output, or table layout.

Contributions are accepted under the project's [Apache-2.0 license](LICENSE).
