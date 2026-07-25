"""Unit tests for the unified `to` console script.

Covers the `to <command> [args...]` dispatcher: pyproject registration,
subcommand registry integrity, and README documentation.
"""

import importlib
import inspect
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
README_MD = REPO_ROOT / "README.md"

EXPECTED_COMMANDS = {
    "backtest": "trader_off.cli.backtest",
    "optimize": "trader_off.portfolio.cli",
    "mine-factors": "trader_off.factor_mining.cli",
    "scheduler": "trader_off.scheduler.cli",
    "sync-data": "trader_off.cli.sync_data",
    "init": "trader_off.cli.init_data",
    "stock-list": "trader_off.cli.stock_list",
    "check-factor": "trader_off.cli.check_factor",
    "paper-trade": "trader_off.cli.paper_trade",
    "grid-search": "trader_off.cli.grid_search",
    "live": "trader_off.cli.live",
    "live-trade": "trader_off.cli.live_trade",
    "generate-strategy": "trader_off.cli.generate_strategy",
    "status": "trader_off.cli.status",
    "server": "trader_off.cli.server",
    "update": "trader_off.cli.update",
}


# ---------------------------------------------------------------------------
# pyproject.toml [project.scripts] registration
# ---------------------------------------------------------------------------


class TestPyprojectScripts:
    @pytest.fixture
    def pyproject_data(self) -> dict:
        with open(PYPROJECT_TOML, "rb") as f:
            return tomllib.load(f)

    def test_project_scripts_table_exists(self, pyproject_data: dict):
        project = pyproject_data.get("project", {})
        assert "scripts" in project, "[project.scripts] table is missing"

    def test_single_to_entry_point(self, pyproject_data: dict):
        """The unified `to` command is the only console script."""
        scripts = pyproject_data.get("project", {}).get("scripts", {})
        assert scripts == {"to": "trader_off.cli.main:main"}, (
            f"Expected single 'to' entry point, got: {scripts}"
        )


# ---------------------------------------------------------------------------
# Dispatcher registry integrity
# ---------------------------------------------------------------------------


class TestDispatcherRegistry:
    def test_registry_matches_expected_commands(self):
        from trader_off.cli.main import _COMMANDS

        actual = {name: module for name, (module, _desc) in _COMMANDS.items()}
        assert actual == EXPECTED_COMMANDS

    @pytest.mark.parametrize(
        "command, module_path",
        sorted(EXPECTED_COMMANDS.items()),
        ids=[name for name, _ in sorted(EXPECTED_COMMANDS.items())],
    )
    def test_subcommand_module_has_callable_main(self, command: str, module_path: str):
        module = importlib.import_module(module_path)
        assert callable(getattr(module, "main", None)), (
            f"{module_path} has no callable main() for 'to {command}'"
        )

    @pytest.mark.parametrize(
        "command, module_path",
        sorted(EXPECTED_COMMANDS.items()),
        ids=[name for name, _ in sorted(EXPECTED_COMMANDS.items())],
    )
    def test_subcommand_main_accepts_optional_argv(self, command: str, module_path: str):
        """Every subcommand main() must accept an optional argv list."""
        module = importlib.import_module(module_path)
        sig = inspect.signature(module.main)
        params = list(sig.parameters.values())
        assert len(params) == 1, (
            f"{module_path}.main should take exactly 1 arg (argv), got {params}"
        )
        assert params[0].default is None, (
            f"{module_path}.main argv param must default to None"
        )


# ---------------------------------------------------------------------------
# Dispatcher behavior
# ---------------------------------------------------------------------------


class TestDispatcherBehavior:
    def test_help_lists_all_commands(self, capsys):
        from trader_off.cli.main import main

        assert main(["--help"]) == 0
        out = capsys.readouterr().out
        for name in EXPECTED_COMMANDS:
            assert name in out, f"help output missing '{name}'"

    def test_no_args_prints_help(self, capsys):
        from trader_off.cli.main import main

        assert main([]) == 0
        assert "usage: to" in capsys.readouterr().out

    def test_unknown_command_returns_2(self, capsys):
        from trader_off.cli.main import main

        assert main(["no-such-command"]) == 2
        assert "unknown command" in capsys.readouterr().err

    def test_dispatches_to_subcommand(self, monkeypatch):
        import trader_off.cli.status as status_mod
        from trader_off.cli.main import main

        captured = {}
        monkeypatch.setattr(
            status_mod, "main", lambda args: captured.setdefault("args", args) or 0
        )
        assert main(["status", "data"]) == 0
        assert captured["args"] == ["data"]


# ---------------------------------------------------------------------------
# README.md documentation
# ---------------------------------------------------------------------------


class TestReadmeUpdates:
    @pytest.fixture
    def readme_text(self) -> str:
        return README_MD.read_text(encoding="utf-8")

    def test_no_legacy_command_names(self, readme_text: str):
        """README must not reference legacy trader-off-* command names."""
        assert "trader-off-" not in readme_text

    def test_python_m_fallback_mention_preserved(self, readme_text: str):
        assert "python -m trader_off" in readme_text, (
            "README must retain at least 1 'python -m trader_off' fallback"
        )

    def test_to_commands_in_readme(self, readme_text: str):
        """README references every subcommand in `to <command>` form."""
        for name in EXPECTED_COMMANDS:
            assert f"to {name}" in readme_text, f"README should mention 'to {name}'"
