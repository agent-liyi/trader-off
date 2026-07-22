"""Tests for NFR-0100: function-scope lazy imports in cli/sync_data.py.

Verifies:
- No top-level quantide imports in sync_data.py
- All quantide imports are inside function bodies (AST verification)
- Whitelisted symbols only:
  quantide.data.fetchers.tushare.* + quantide.data.models.calendar.calendar
- No blacklisted quantide submodules
"""

import ast
import subprocess
from pathlib import Path

import pytest

SRC_FILE = Path("src/trader_off/cli/sync_data.py")

# Blacklisted quantide submodules per NFR-0100
BLACKLISTED = [
    "quantide.service",
    "quantide.portfolio",
    "quantide.backtest",
    "quantide.core.scheduler",
    "quantide.data.models.daily_bars",
]


# ---------------------------------------------------------------------------
# AST verification
# ---------------------------------------------------------------------------


class TestNFR0100AST:
    """NFR-0100: AST-level verification of lazy imports."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_file(self):
        """Skip AST tests if sync_data.py doesn't exist yet (Red phase)."""
        if not SRC_FILE.exists():
            pytest.skip("sync_data.py not yet created (Red phase)")

    def test_no_top_level_quantide_imports(self):
        """AC-NFR0100-04: AST parse confirms no quantide import at module top level."""
        tree = ast.parse(SRC_FILE.read_text())

        # Only check direct children of the module (top-level statements)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module_name = _get_module_name(node)
                if module_name and (
                    module_name == "quantide" or module_name.startswith("quantide.")
                ):
                    pytest.fail(
                        f"quantide import '{module_name}' at line {node.lineno} "
                        f"is at module top level — must be function-scoped (NFR-0100)"
                    )

    def test_no_blacklisted_quantide_submodules(self):
        """NFR-0100: No blacklisted quantide submodules in entire file."""
        content = SRC_FILE.read_text()
        for banned in BLACKLISTED:
            assert banned not in content, (
                f"Blacklisted quantide import '{banned}' found in sync_data.py (NFR-0100)"
            )

    def test_whitelisted_fetch_calendar_import_present(self):
        """NFR-0100: Whitelisted tushare import exists."""
        content = SRC_FILE.read_text()
        assert "from quantide.data.fetchers.tushare import" in content, (
            "Missing whitelisted import: quantide.data.fetchers.tushare (NFR-0100)"
        )

    def test_whitelisted_calendar_import_present(self):
        """NFR-0100: Whitelisted calendar import exists."""
        content = SRC_FILE.read_text()
        assert "quantide.data.models.calendar" in content, (
            "Missing whitelisted import: quantide.data.models.calendar (NFR-0100)"
        )


# ---------------------------------------------------------------------------
# Grep verification (independently verifies the AST test)
# ---------------------------------------------------------------------------


class TestNFR0100Grep:
    """NFR-0100: Grep-based verification of lazy imports."""

    def test_no_top_level_import_quantide(self):
        """Grep: no 'import quantide' or 'from quantide' at module top level."""
        if not SRC_FILE.exists():
            pytest.skip("sync_data.py not yet created (Red phase)")

        # "^import quantide\|^from quantide" — lines starting with import/from quantide
        result = subprocess.run(
            [
                "grep",
                "-n",
                "-e",
                "^import quantide",
                "-e",
                "^from quantide",
                str(SRC_FILE),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"Top-level quantide import found in sync_data.py:\n{result.stdout}"
        )

    def test_no_blacklisted_symbols_grep(self):
        """Grep: no blacklisted quantide symbols in sync_data.py."""
        if not SRC_FILE.exists():
            pytest.skip("sync_data.py not yet created (Red phase)")

        # Use perl-compatible regex with alternation
        result = subprocess.run(
            [
                "grep",
                "-nE",
                r"quantide\.(service|portfolio|backtest|core\.scheduler|data\.models\.daily_bars)",
                str(SRC_FILE),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"Blacklisted quantide symbol found in sync_data.py:\n{result.stdout}"
        )

    def test_cli_dir_isolation(self):
        """NFR-0100 verify 5: no quantide top-level imports in cli/ directory."""
        # Check all cli/*.py files for module-level quantide imports
        result = subprocess.run(
            [
                "grep",
                "-rn",
                "-e",
                "^import quantide",
                "-e",
                "^from quantide",
                "src/trader_off/cli/",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, (
            f"Top-level quantide import in cli/ directory:\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_module_name(node: ast.AST) -> str | None:
    """Extract the module name from an Import or ImportFrom node."""
    if isinstance(node, ast.Import):
        return node.names[0].name if node.names else None
    elif isinstance(node, ast.ImportFrom):
        return node.module
    return None
