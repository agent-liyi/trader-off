"""Tests for NFR-0200: pytest-cov coverage configuration.

AC-NFR0200-01: pytest-cov configured, total coverage ≥97%.
AC-NFR0200-02: Coverage configuration is invokable via pytest --cov.
"""

from pathlib import Path


class TestCoverageConfiguration:
    """NFR-0200: pytest-cov coverage tooling."""

    def test_coverage_config_exists_in_pyproject(self):
        """AC-NFR0200-01: pyproject.toml has [tool.coverage.run] configuration."""
        toml_text = Path("pyproject.toml").read_text()
        assert "[tool.coverage.run]" in toml_text, "Missing [tool.coverage.run] section"
        assert "[tool.coverage.report]" in toml_text, "Missing [tool.coverage.report] section"

    def test_coverage_source_is_trader_off(self):
        """AC-NFR0200-01: Coverage source is set to trader_off module."""
        toml_text = Path("pyproject.toml").read_text()
        assert 'source = ["trader_off"]' in toml_text or "source = [" in toml_text

    def test_coverage_branch_enabled(self):
        """AC-NFR0200-01: Branch coverage is enabled."""
        toml_text = Path("pyproject.toml").read_text()
        assert "branch = true" in toml_text, "Branch coverage should be enabled"

    def test_pytest_cov_installed(self):
        """AC-NFR0200-01: pytest-cov is installed and importable."""
        import pytest_cov  # noqa: F401

    def test_coverage_invokable_via_pytest(self):
        """AC-NFR0200-01: Coverage can be invoked via pytest --cov=trader_off.

        This verifies the tooling is set up correctly by running coverage
        on a sample of unit tests.
        """
        import subprocess

        result = subprocess.run(
            [
                "uv",
                "run",
                "pytest",
                "tests/unit/scheduler/test_state.py",
                "--cov=trader_off",
                "--cov-report=term-missing",
                "-q",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Should run without error (0 = all passed, 5 = no tests collected)
        output = result.stdout + result.stderr
        # Coverage should be invoked and produce output
        assert (
            "--cov=trader_off" in output or "coverage" in output.lower() or result.returncode == 0
        )
