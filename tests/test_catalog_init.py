import io
import json
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from infra.lakekeeper import init_catalog


def test_credentials_are_serialized_not_interpolated():
    secret = 'quote" backslash\\ newline\n'
    payload = json.loads(json.dumps(init_catalog.warehouse_payload('user"', secret)))
    assert payload["storage-credential"]["secret-access-key"] == secret
    assert payload["storage-credential"]["access-key-id"] == 'user"'


@pytest.mark.parametrize(("body", "accepted"), [
    (b'{"type":"CatalogAlreadyBootstrapped"}', True), (b'{"type":"UnexpectedConflict"}', False),
    (b'{"error":{"type":"CatalogAlreadyBootstrapped","code":400}}', True),
    (b'not json', False), (b'[]', False),
])
def test_only_expected_catalog_errors_are_accepted(monkeypatch, body, accepted):
    error = HTTPError("http://local", 400, "bad request", {}, io.BytesIO(body))
    monkeypatch.setattr(init_catalog, "urlopen", Mock(side_effect=error))
    if accepted:
        init_catalog.post("bootstrap", {}, {"CatalogAlreadyBootstrapped"})
    else:
        with pytest.raises(RuntimeError, match="HTTP 400"):
            init_catalog.post("bootstrap", {}, {"CatalogAlreadyBootstrapped"})
