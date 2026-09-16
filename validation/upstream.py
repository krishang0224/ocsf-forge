"""Explicit opt-in validation of bundled synthetic fixtures by the OCSF server."""

import json
import urllib.request

BASE = "https://schema.ocsf.io/1.8.0/api"


def verify_version():
    with urllib.request.urlopen(f"{BASE}/version", timeout=30) as response:
        version = json.load(response)["version"]
    if version != "1.8.0":
        raise ValueError(f"Unexpected upstream OCSF version: {version}")


def validate(record):
    request = urllib.request.Request(
        f"{BASE}/v2/validate", data=json.dumps(record).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if not isinstance(result, dict) or not isinstance(result.get("errors"), list) or type(result.get("error_count")) is not int:
        raise ValueError("Upstream validator returned an unexpected response")
    if result["error_count"] != len(result["errors"]):
        raise ValueError("Upstream validator returned inconsistent error counts")
    return result
