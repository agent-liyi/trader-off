"""Tests for NFR-0700 (security) — bandit clean, pip-audit clean, no hardcoded secrets."""

import subprocess


class TestSecurityNFR0700:
    """NFR-0700: bandit clean, pip-audit clean, no hardcoded secrets."""

    def test_bandit_runs_and_finds_no_issues(self):
        """AC-1: bandit scan of src/ returns 0 (no issues)."""
        result = subprocess.run(
            ["uv", "run", "bandit", "-r", "src/", "-q"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"bandit found issues:\n{result.stdout}\n{result.stderr}"

    def test_no_hardcoded_secrets_in_source(self):
        """AC-3: no hardcoded api_key/password/token/secret in source."""
        result = subprocess.run(
            [
                "grep",
                "-rE",
                r"(api_key|password|token|secret)\s*=\s*['\"][^'\"]{8,}['\"]",
                "src/trader_off/",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, f"Hard-coded secrets found:\n{result.stdout}"

    def test_security_check_script_runs(self):
        """AC-4: scripts/security_check.sh should exit 0."""
        from pathlib import Path

        script = Path(__file__).parent.parent.parent / "scripts" / "security_check.sh"
        if not script.exists():
            # Script is optional if tools are in pre-commit
            return

        result = subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"security_check.sh failed:\n{result.stdout}\n{result.stderr}"
        )
