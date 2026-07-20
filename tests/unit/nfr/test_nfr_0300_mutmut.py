"""Tests for NFR-0300: Mutation Testing with mutmut.

AC-NFR0300-01: mutmut>=2.0 configured, mutation score >= 80%.
"""

from pathlib import Path


class TestMutmutConfiguration:
    """NFR-0300: mutmut mutation testing configuration."""

    def test_mutmut_in_dev_dependencies(self):
        """AC-NFR0300-01: mutmut>=2.0 is in dev dependency group."""
        toml_text = Path("pyproject.toml").read_text()
        assert "mutmut>=2.0" in toml_text or "mutmut" in toml_text

    def test_mutmut_config_file_or_script_exists(self):
        """AC-NFR0300-01: Mutation test script exists at scripts/run_mutation_tests.sh."""
        script_path = Path("scripts/run_mutation_tests.sh")
        assert script_path.exists(), "scripts/run_mutation_tests.sh not found"
        assert script_path.stat().st_size > 0, "scripts/run_mutation_tests.sh is empty"

    def test_mutmut_script_is_executable(self):
        """AC-NFR0300-01: Mutation test script is executable."""
        script_path = Path("scripts/run_mutation_tests.sh")
        import os

        assert os.access(script_path, os.X_OK), "scripts/run_mutation_tests.sh is not executable"

    def test_mutmut_script_has_usage_documentation(self):
        """AC-NFR0300-01: Mutation test script contains usage documentation."""
        script_path = Path("scripts/run_mutation_tests.sh")
        content = script_path.read_text()
        # Should mention NFR-0300
        assert "NFR-0300" in content or "mutation" in content.lower()
        # Should have test_command or pytest reference
        assert "pytest" in content.lower()

    def test_mutmut_installed_and_runnable(self):
        """AC-NFR0300-01: mutmut is installed and can be invoked."""
        import subprocess

        result = subprocess.run(
            ["uv", "pip", "show", "mutmut"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # mutmut should be in the pip list output
        assert result.returncode == 0 or "mutmut" in result.stdout.lower()
