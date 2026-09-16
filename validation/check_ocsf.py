"""Print an honest, offline fixture audit: python -m validation.check_ocsf."""

import argparse
import hashlib
import json

from validation.fixtures import FIXTURES, cases, export
from validation.ocsf_contract import check


def audit():
    provenance = json.loads((FIXTURES / "provenance.json").read_text())
    results = []
    for case in cases():
        path = FIXTURES / "contracts" / f"{case['contract']}.json"
        if hashlib.sha256(path.read_bytes()).hexdigest() != provenance["contracts"][case["contract"]]["sha256"]:
            raise ValueError(f"Contract snapshot hash mismatch: {path.name}")
        record = export(case)
        expected = json.loads((FIXTURES / "expected" / f"{case['name']}.json").read_text())
        errors = check(record, json.loads(path.read_text()))
        if record != expected:
            errors.append("export differs from committed fixture")
        results.append({"fixture": case["name"], "class_uid": record["class_uid"], "errors": errors})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-baseline", action="store_true", help="check documented known gaps, NOT conformance")
    parser.add_argument("--live", action="store_true", help="send only bundled synthetic fixtures to the official OCSF 1.8.0 validator")
    args = parser.parse_args()
    if args.live and args.check_baseline:
        parser.error("--live and --check-baseline are separate checks")
    try:
        if args.live:
            from validation.upstream import validate, verify_version

            verify_version()
            failures = 0
            for case in cases():
                result = validate(export(case))
                print(json.dumps({"fixture": case["name"], "upstream": result}), flush=True)
                failures += result["error_count"] > 0
            return 1 if failures else 0
        results = audit()
        for result in results:
            print(json.dumps(result))
        failures = sum(bool(result["errors"]) for result in results)
        print(json.dumps({"check": "partial top-level OCSF 1.8.0 contract", "fixtures": len(results), "failed": failures,
                          "full_schema_conformance": "not established"}))
        if args.check_baseline:
            expected = json.loads((FIXTURES / "known-gaps.json").read_text())
            return 0 if results == expected else 1
        return 1 if failures else 0
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
