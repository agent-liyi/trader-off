"""Tests for pyproject.toml configuration — FR-0100/FR-0200."""

import sys
import tomllib
from pathlib import Path

import pytest

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


QUANTIDE_DEP = "quantide @ git+https://github.com/agent-liyi/millionaire.git"


class TestPyprojectQuantideDep:
    """FR-0200: quantide dependency in pyproject.toml."""

    # AC-FR0200-01: quantide @ git+... in dependencies
    def test_quantide_in_dependencies(self):
        """pyproject.toml dependencies include quantide @ git URL."""
        data = _load_pyproject()
        deps = data["project"]["dependencies"]
        assert QUANTIDE_DEP in deps, f"quantide git URL not found in dependencies: {deps}"

    # AC-FR0200-04: only compat.py directly imports quantide
    def test_only_compat_imports_quantide(self):
        """no other source files directly import quantide."""
        src = Path("src/trader_off")
        violators = []
        for f in src.rglob("*.py"):
            if f.name == "compat.py":
                continue
            text = f.read_text()
            if "import quantide" in text:
                violators.append(str(f))
        assert violators == [], f"Files importing quantide: {violators}"

    # AC-FR0200-05: verify quantide is importable after uv sync
    def test_quantide_importable(self):
        """quantide package can be imported."""
        try:
            import quantide  # noqa: F401
        except ImportError as e:
            pytest.fail(f"quantide not importable: {e}")
