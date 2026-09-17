"""Offline per-fixture gate using the official OCSF Toolkit, not snapshots."""

import argparse
import json
import subprocess
from pathlib import Path

from validation.fixtures import cases, export
from validation.toolkit import bundle, validate

EXPECTED = Path(__file__).with_name("expected-results.json")


def audit(directory):
    executable, schema = bundle(directory)
    expected = json.loads(EXPECTED.read_text())
    fixtures = cases()
    names = [case["name"] for case in fixtures]
    if len(names) != len(set(names)) or set(names) != set(expected):
        raise ValueError("Fixture set differs from the explicit toolkit expectations")
    results = []
    for case in fixtures:
        actual = validate(export(case), executable, schema)
        results.append({"fixture": case["name"], "findings": actual,
                        "expected": expected[case["name"]], "matched": actual == expected[case["name"]]})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".cache/ocsf-validator"))
    args = parser.parse_args()
    try:
        results = audit(args.directory)
        for result in results:
            print(json.dumps(result))
        return 0 if all(result["matched"] for result in results) else 1
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"validator_infrastructure_error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
