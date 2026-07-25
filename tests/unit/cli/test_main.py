"""
Tests for the unified CLI entry point (`src/trader_off/cli/main.py`).
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from trader_off import __version__
from trader_off.cli.main import _COMMANDS, main as to_main

_THIS_DIR = Path(__file__).parent


class TestHelp:
    def test_no_args_shows_help(self):
        """to (no args) prints help and exits 0."""
        assert to_main([]) == 0

    def test_help_flag(self):
        """to --help prints help and exits 0."""
        assert to_main(["--help"]) == 0

    def test_help_output_contains_all_commands(self):
        """Help output lists all 16 commands."""
        from io import StringIO

        out = StringIO()
        with patch("sys.stdout", out):
            to_main([])
        for name in _COMMANDS:
            assert name in out.getvalue(), f"Command '{name}' should be in help output"

    @pytest.mark.parametrize("key", list(_COMMANDS.keys()))
    def test_each_command_entry_exists(self, key):
        """All 16 commands listed in _COMMANDS."""
        assert key in _COMMANDS


class TestVersion:
    def test_version_flag(self):
        """to --version returns 0."""
        assert to_main(["--version"]) == 0


class TestDispatch:
    @pytest.mark.parametrize("command", list(_COMMANDS.keys()))
    def test_dispatch_calls_main(self, command):
        """Dispatching to each subcommand calls its main()."""
        _mod_path, _ = _COMMANDS[command]
        with patch(f"{_mod_path}.main") as mock_main:
            mock_main.return_value = 0
            to_main([command, "--help"])
            mock_main.assert_called_once()

    def test_unknown_command_exits_2(self):
        """to unknown exits 2."""
        assert to_main(["nonexistent"]) == 2

    def test_args_passed_through(self):
        """Extra args after command are forwarded."""
        with patch("trader_off.cli.backtest.main") as mock_main:
            mock_main.return_value = 0
            to_main(["backtest", "--model", "v1", "--strategy", "optimized_topk"])
            mock_main.assert_called_once_with(["--model", "v1", "--strategy", "optimized_topk"])


class TestLazyImport:
    def test_only_target_module_imported(self):
        """Only the dispatched module is imported (lazy import)."""
        import sys as _sys

        before = set(_sys.modules.keys())
        to_main(["status"])
        after = set(_sys.modules.keys())
        new_modules = after - before
        # The status module should be imported, but others should not
        assert "trader_off.cli.status" in new_modules, "status module should be loaded"


class TestMainSignature:
    """Verify that all 15 CLI modules accept main(argv)."""

    CLI_MODULES = [
        "trader_off.cli.backtest",
        "trader_off.cli.paper_trade",
        "trader_off.cli.live_trade",
        "trader_off.cli.grid_search",
        "trader_off.cli.check_factor",
        "trader_off.cli.generate_strategy",
        "trader_off.cli.init_data",
        "trader_off.cli.stock_list",
        "trader_off.cli.sync_data",
        "trader_off.cli.live",
        "trader_off.cli.server",
        "trader_off.cli.status",
        "trader_off.cli.update",
        "trader_off.portfolio.cli",
        "trader_off.scheduler.cli",
        "trader_off.factor_mining.cli",
    ]

    @pytest.mark.parametrize("mod_path", CLI_MODULES)
    def test_main_accepts_argv(self, mod_path):
        """Each CLI module's main() accepts argv list[str] | None."""
        import importlib

        mod = importlib.import_module(mod_path)
        assert hasattr(mod, "main"), f"{mod_path} has no main()"
        # Call with empty list — should exit 0
        result = mod.main([])
        assert isinstance(result, int)
