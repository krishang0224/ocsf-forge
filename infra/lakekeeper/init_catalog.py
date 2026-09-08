"""Initialize the local catalog without interpolating credentials into JSON."""

import json
import os
import signal
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def post(path, payload, allowed_errors):
    request = Request(
        f"http://lakekeeper:8181/management/v1/{path}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            if response.status not in {200, 201, 204}:
                raise RuntimeError(f"Catalog {path} returned HTTP {response.status}")
    except HTTPError as exc:
        if exc.code in {400, 409}:
            try:
                error = json.loads(exc.read())
            except (ValueError, UnicodeDecodeError):
                error = {}
            if isinstance(error, dict):
                error = error.get("error", error)
            if isinstance(error, dict) and error.get("type") in allowed_errors:
                return
        raise RuntimeError(f"Catalog {path} failed with HTTP {exc.code}") from None


def warehouse_payload(access_key, secret_key):
    return {
        "warehouse-name": "ulpf", "project-id": "00000000-0000-0000-0000-000000000000",
        "storage-profile": {
            "type": "s3", "bucket": "lakehouse-warehouse", "key-prefix": "ulpf", "endpoint": "http://minio:9000",
            "region": "us-east-1", "path-style-access": True, "flavor": "s3-compat", "sts-enabled": False,
        },
        "storage-credential": {
            "type": "s3", "credential-type": "access-key", "access-key-id": access_key, "secret-access-key": secret_key,
        },
        "delete-profile": {"type": "hard"},
    }


def main():
    post("bootstrap", {"accept-terms-of-use": True}, {"CatalogAlreadyBootstrapped"})
    post("warehouse", warehouse_payload(os.environ["MINIO_ROOT_USER"], os.environ["MINIO_ROOT_PASSWORD"]),
         {"CreateWarehouseStorageProfileOverlap", "WarehouseAlreadyExists"})
    Path("/tmp/ready").touch()
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    stopped.wait()


if __name__ == "__main__":
    main()
