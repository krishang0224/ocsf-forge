import tomllib
from pathlib import Path


def test_packaging_keeps_core_independent_and_reuses_dependency_pins():
    metadata = tomllib.loads(Path("pyproject.toml").read_text())
    assert metadata["project"]["dependencies"] == []
    assert metadata["project"]["scripts"]["ocsf-forge"] == "ulpf.cli:main"
    dynamic = metadata["tool"]["setuptools"]["dynamic"]
    assert dynamic["version"] == {"attr": "ulpf.__version__"}
    assert dynamic["optional-dependencies"]["homelab"] == {"file": ["requirements-homelab.txt"]}
    assert dynamic["optional-dependencies"]["lakehouse"] == {"file": ["requirements.txt"]}
