import importlib.util
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec("duckdb") is None, reason="requires requirements-homelab.txt")


def test_explicit_homelab_ui_without_lakehouse_imports_or_connections(tmp_path):
    code = """
import socket
import sys
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

# Streamlit 1.49 AppTest treats a single-select segmented value as a character list.
with patch.object(socket.socket, 'connect', side_effect=AssertionError('Unexpected network connection')), \\
     patch('streamlit.segmented_control', return_value='Sample'):
    app = AppTest.from_file('app.py').run(timeout=30)
    assert not app.exception, app.exception
    assert app.metric[0].value == '0'
    next(button for button in app.button if button.label == 'Ingest into DuckDB').click().run(timeout=30)
    assert not app.exception, app.exception
    assert app.metric[0].value == '8'
    next(button for button in app.button if button.label == 'Ingest into DuckDB').click().run(timeout=30)
    assert any('8 duplicates' in item.value for item in app.success)
    next(button for button in app.button if button.label == 'Run query').click().run(timeout=30)
    assert not app.exception, app.exception
    assert any('rows shown' in item.value for item in app.success)
    assert 'Local storage' in [tab.label for tab in app.tabs]
    assert 'Findings' not in [tab.label for tab in app.tabs]
assert not any(name.split('.')[0] in {'trino', 'minio', 'kafka'} for name in sys.modules)
print('homelab UI passed without network connections or lakehouse imports')
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=90,
        env={**os.environ, "ULPF_BACKEND": "duckdb", "ULPF_HOMELAB_DIRECTORY": str(tmp_path)},
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_default_configuration_remains_trino():
    env = {key: value for key, value in os.environ.items() if not key.startswith("ULPF_")}
    result = subprocess.run(
        [sys.executable, "-c", "from ulpf.config import settings; assert settings.backend == 'trino'"],
        capture_output=True, text=True, timeout=15, env=env,
    )
    assert result.returncode == 0, result.stderr


def test_isolated_environment_has_no_lakehouse_dependencies():
    if os.getenv("HOMELAB_ISOLATED") != "1":
        pytest.skip("run with HOMELAB_ISOLATED=1 in the homelab-only environment")
    for module in ("trino", "minio", "kafka"):
        assert importlib.util.find_spec(module) is None


def test_trino_app_does_not_load_duckdb_or_fall_back(tmp_path):
    pytest.importorskip("trino")
    pytest.importorskip("minio")
    code = """
import sys
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
with patch('ulpf.services.trino.TrinoService.health', return_value=(False, 'offline')), \\
     patch('ulpf.services.minio.MinioService.status', return_value={'ready': False, 'error': 'offline'}):
    app = AppTest.from_file('app.py').run(timeout=30)
assert not app.exception, app.exception
assert any(button.label == 'Ingest into Iceberg' for button in app.button)
assert not any(button.label == 'Ingest into DuckDB' for button in app.button)
assert 'duckdb' not in sys.modules
assert 'ulpf.ui.homelab' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=45,
        env={**os.environ, "ULPF_BACKEND": "trino", "ULPF_HOMELAB_DIRECTORY": str(tmp_path / "unused")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "unused").exists()
