"""Fetch verified upstream artifacts and compile the pinned base schema (Python 3.14+)."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

LOCK = Path(__file__).with_name("toolchain-lock.json")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_archive(pin, archive):
    if not archive.exists():
        with urllib.request.urlopen(pin["url"], timeout=60) as response:
            payload = response.read(64 * 1024 * 1024 + 1)
        if len(payload) > 64 * 1024 * 1024:
            raise ValueError("Upstream archive exceeds the 64 MiB setup limit")
        archive.write_bytes(payload)
    if digest(archive) != pin["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {archive.name}; remove the corrupt archive before retrying")


def prepare(destination):
    if sys.version_info < (3, 14):
        raise ValueError("Schema preparation requires Python 3.14+; application tests remain on Python 3.11")
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise ValueError("The pinned validation toolchain currently supports Linux x86_64 only")
    destination.mkdir(parents=True, exist_ok=True)
    pins = json.loads(LOCK.read_text())
    for name, pin in pins.items():
        archive = destination / f"{name}.tar.gz"
        fetch_archive(pin, archive)
        with tarfile.open(archive) as source:
            source.extractall(destination, filter="data")
    environment = {**os.environ, "PYTHONPATH": str(destination / pins["compiler"]["root"] / "src")}
    compiled = subprocess.run(
        [sys.executable, "-m", "ocsf_schema_compiler", "--ignore-platform-extensions",
         "--log-level", "WARNING", str(destination / pins["schema"]["root"])],
        env=environment, capture_output=True, check=True, timeout=120,
    )
    document = json.loads(compiled.stdout)
    if document.get("version") != pins["schema"]["version"] or document.get("compile_version") != 1:
        raise ValueError("Unexpected compiled schema version or format")
    if compiled.stderr.strip():
        raise ValueError(f"Schema compiler diagnostics: {compiled.stderr.decode()}")
    schema = destination / "compiled.json"
    schema.write_bytes(compiled.stdout)
    executable = destination / pins["toolkit"]["root"] / "ocsf-toolkit"
    version = subprocess.run([str(executable), "--version"], capture_output=True, text=True, check=True, timeout=10)
    if version.stdout.strip() != f"ocsf-toolkit {pins['toolkit']['version']}":
        raise ValueError("Unexpected toolkit version")
    manifest = {"lock_sha256": digest(LOCK), "schema_sha256": digest(schema),
                "executable": str(executable.relative_to(destination)), "executable_sha256": digest(executable)}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".cache/ocsf-validator"))
    args = parser.parse_args()
    try:
        prepare(args.directory.resolve())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print(f"Validator setup failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
