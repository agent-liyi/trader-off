"""Tests for NFR-0800 (data reproducibility) — deterministic seeds, frozen deps."""

from pathlib import Path

import numpy as np
import pytest

from trader_off.utils.random import set_seed


class TestReproducibilityNFR0800:
    """NFR-0800: deterministic random seeds, frozen deps, fixture versioning."""

    def test_set_seed_produces_deterministic_numpy_output(self):
        """AC-1: same seed → same numpy output sequence."""
        set_seed(42)
        a1 = np.random.rand(5)

        set_seed(42)
        a2 = np.random.rand(5)

        assert np.allclose(a1, a2), "Same seed should produce identical numpy output"

    def test_set_seed_produces_deterministic_python_random_output(self):
        """AC-1: same seed → same Python random output sequence."""
        import random

        set_seed(123)
        r1 = [random.random() for _ in range(5)]

        set_seed(123)
        r2 = [random.random() for _ in range(5)]

        assert r1 == r2, "Same seed should produce identical Python random output"

    def test_set_seed_requires_explicit_seed(self):
        """AC-1: set_seed(None) should raise ValueError."""
        with pytest.raises(ValueError, match="seed must be provided"):
            set_seed(None)

    def test_set_seed_rejects_negative_seed(self):
        """AC-1: set_seed(-1) should raise ValueError."""
        with pytest.raises(ValueError, match="seed must be non-negative"):
            set_seed(-1)

    def test_determinism_two_libraries_same_seed(self):
        """AC-1: numpy and Python random produce consistent results with same seed."""
        set_seed(999)
        np_out = np.random.rand(3)
        import random

        py_out = [random.random() for _ in range(3)]

        # Reset and verify both produce same sequences
        set_seed(999)
        np_out2 = np.random.rand(3)
        set_seed(999)
        py_out2 = [random.random() for _ in range(3)]

        assert np.allclose(np_out, np_out2)
        assert py_out == py_out2

    def test_uv_lock_file_exists(self):
        """AC-2: uv.lock should exist for frozen dependency versions."""
        lock_file = Path("uv.lock")
        assert lock_file.exists(), "uv.lock must exist for reproducible builds"

    def test_lock_file_is_valid_toml(self):
        """AC-2: uv.lock should be valid TOML."""
        import tomllib

        lock_file = Path("uv.lock")
        with open(lock_file, "rb") as f:
            data = tomllib.load(f)
        assert isinstance(data, dict), "uv.lock should parse to a dict"
        assert "version" in data or "metadata" in data, "uv.lock should have version/metadata"

    def test_pyproject_toml_has_locked_versions(self):
        """AC-2: pyproject.toml dependencies should have version constraints."""
        import tomllib

        pyproject = Path("pyproject.toml")
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)

        deps = data.get("project", {}).get("dependencies", [])
        assert len(deps) > 0, "pyproject.toml should declare dependencies"

        # Each dep should have a version specifier (>=, ~=, ==, etc.)
        for dep in deps:
            # Format: "package>=version" or "package>=version,<upper"
            assert ">=" in dep or "~=" in dep or "==" in dep, (
                f"Dependency {dep} should have explicit version constraint"
            )
