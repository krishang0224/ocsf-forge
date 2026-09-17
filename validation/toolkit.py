"""Strict adapter for the pinned, validation-only upstream toolkit CLI."""

import json
import subprocess
import tempfile
from pathlib import Path

from validation.prepare_toolkit import LOCK, digest


def bundle(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    executable = (directory / manifest["executable"]).resolve()
    if not executable.is_relative_to(directory):
        raise ValueError("Validator executable escapes its bundle directory")
    schema = directory / "compiled.json"
    if (manifest["lock_sha256"] != digest(LOCK) or manifest["schema_sha256"] != digest(schema)
            or manifest["executable_sha256"] != digest(executable)):
        raise ValueError("Validator bundle does not match its preparation manifest or toolchain lock")
    return executable, schema


def signatures(report):
    if not isinstance(report, dict) or type(report.get("report_version")) is not int or report["report_version"] != 1:
        raise ValueError("Unsupported toolkit report")
    if report.get("issues"):
        raise ValueError(f"Toolkit reported incomplete processing: {report['issues']}")
    validation = report.get("validation")
    if not isinstance(validation, dict):
        raise ValueError("Toolkit did not return a validation result")
    findings = validation.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("Malformed toolkit findings")
    result = []
    for finding in findings:
        try:
            signature = [finding["level"], finding["code"], finding["details"]["attribute_path"]]
        except (KeyError, TypeError) as exc:
            raise ValueError("Malformed toolkit finding") from exc
        if not all(isinstance(value, str) and value for value in signature):
            raise ValueError("Malformed toolkit finding signature")
        result.append(signature)
    return sorted(result)


def validate(record, executable, schema):
    with tempfile.TemporaryDirectory(prefix="ocsf-event-") as temp:
        path = Path(temp) / "event.json"
        path.write_text(json.dumps(record, allow_nan=False))
        process = subprocess.run(
            [str(executable), "--schema", str(schema), "--event", str(path),
             "--validate", "--report-output", "-"],
            capture_output=True, text=True, timeout=30, check=True,
        )
    if process.stderr.strip():
        raise ValueError(f"Toolkit initialization diagnostics: {process.stderr}")
    report = json.loads(process.stdout)
    return signatures(report)
