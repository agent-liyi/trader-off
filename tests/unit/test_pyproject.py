"""Tests for pyproject.toml configuration — FR-0100: Python 3.13 upgrade."""

import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"


def _load_pyproject() -> dict:
    """Load pyproject.toml as a dict."""
    return tomllib.loads(PYPROJECT_PATH.read_text())


class TestPyprojectPython313:
    """FR-0100: pyproject.toml targets Python 3.13."""

    # AC-FR0100-01: requires-python == ">=3.13"
    def test_requires_python_313(self):
        """pyproject.toml has requires-python >=3.13."""
        data = _load_pyproject()
        assert data["project"]["requires-python"] == ">=3.13", (
            f"Expected >=3.13, got {data['project']['requires-python']}"
        )

    # AC-FR0100-02: ruff target-version py313, mypy python_version 3.13
    def test_ruff_target_version_py313(self):
        """[tool.ruff].target-version == py313."""
        data = _load_pyproject()
        assert data["tool"]["ruff"]["target-version"] == "py313", (
            f"Expected py313, got {data['tool']['ruff']['target-version']}"
        )

    def test_mypy_python_version_313(self):
        """[tool.mypy].python_version == 3.13."""
        data = _load_pyproject()
        assert data["tool"]["mypy"]["python_version"] == "3.13", (
            f"Expected 3.13, got {data['tool']['mypy']['python_version']}"
        )

    # AC-FR0100-03: uv sync and pytest succeed on Python >=3.13
    def test_python_version_is_at_least_313(self):
        """Current Python interpreter is >=3.13."""
        version = sys.version_info
        assert (version.major, version.minor) >= (3, 13), (
            f"Python {version.major}.{version.minor} is too old"
        )
