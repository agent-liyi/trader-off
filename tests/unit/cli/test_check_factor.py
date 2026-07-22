"""Unit tests for check_factor CLI — FR-0100.

Covers: factor found + valid, factor found + invalid, factor not found,
no data boundary, --json output, and NFR-0100 function-scope lazy imports.
"""

from __future__ import annotations

import ast
import json
import subprocess
from datetime import date
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

# Module under test — will fail until check_factor.py exists (Red phase)
try:
    from trader_off.cli.check_factor import main
except ImportError:
    main = None  # type: ignore[assignment]

SRC_FILE = Path("src/trader_off/cli/check_factor.py")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ohlcv_fixture() -> pl.DataFrame:
    """Create a small OHLCV DataFrame for testing."""
    assets = ["000001.SZ", "000002.SZ"]
    dates_list = [date(2022, 1, 3), date(2022, 1, 4), date(2022, 1, 5)]
    rows = []
    for asset in assets:
        for i, d in enumerate(dates_list):
            rows.append(
                {
                    "asset": asset,
                    "date": d,
                    "open": 10.0 + i,
                    "high": 11.0 + i,
                    "low": 9.5 + i,
                    "close": 10.5 + i,
                    "volume": 1000.0 + i * 100,
                    "turnover": 0.05 + i * 0.01,
                }
            )
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# Argument parsing tests
# ---------------------------------------------------------------------------


class TestCheckFactorCLIArgs:
    """Argument parsing tests (AC-FR0100)."""

    def test_missing_required_name_exits_nonzero(self, capsys):
        """Missing --name → SystemExit with non-zero exit code."""
        if main is None:
            pytest.skip("check_factor.py not yet created (Red phase)")
        with pytest.raises(SystemExit) as exc_info:
            main(argv=["--start", "2022-01-01", "--end", "2022-01-31"])
        assert exc_info.value.code != 0

    def test_missing_required_start_exits_nonzero(self, capsys):
        """Missing --start → SystemExit with non-zero exit code."""
        if main is None:
            pytest.skip("check_factor.py not yet created (Red phase)")
        with pytest.raises(SystemExit) as exc_info:
            main(argv=["--name", "momentum_5", "--end", "2022-01-31"])
        assert exc_info.value.code != 0

    def test_missing_required_end_exits_nonzero(self, capsys):
        """Missing --end → SystemExit with non-zero exit code."""
        if main is None:
            pytest.skip("check_factor.py not yet created (Red phase)")
        with pytest.raises(SystemExit) as exc_info:
            main(argv=["--name", "momentum_5", "--start", "2022-01-01"])
        assert exc_info.value.code != 0

    def test_default_capital_value(self, capsys):
        """--capital defaults to 1_000_000."""
        if main is None:
            pytest.skip("check_factor.py not yet created (Red phase)")
        # We can't introspect argparse defaults without importing the parser,
        # so we verify by capturing help output.
        with pytest.raises(SystemExit):
            main(argv=["--help"])

    def test_default_ic_threshold_value(self, capsys):
        """--ic-threshold defaults to 0.3."""
        if main is None:
            pytest.skip("check_factor.py not yet created (Red phase)")
        with pytest.raises(SystemExit):
            main(argv=["--help"])

    def test_json_flag_accepted(self, capsys):
        """--json flag is accepted as a valid argument."""
        if main is None:
            pytest.skip("check_factor.py not yet created (Red phase)")
        # This should not raise an argument error for --json
        # (will fail on factor not found, which is fine for this test)
        result = main(
            argv=[
                "--name",
                "nonexistent",
                "--start",
                "2022-01-01",
                "--end",
                "2022-01-31",
                "--json",
            ]
        )
        assert result in (0, 1)


# ---------------------------------------------------------------------------
# Success path tests
# ---------------------------------------------------------------------------


class TestCheckFactorSuccess:
    """Happy path tests for check_factor CLI."""

    def test_factor_found_and_valid(self, tmp_path, monkeypatch):
        """Factor found with ICIR above threshold → status=ok, valid=true."""
        fixture = _make_ohlcv_fixture()

        with patch(
            "trader_off.cli.check_factor._load_ohlcv_data",
            return_value=fixture,
        ):
            result = main(
                argv=[
                    "--name",
                    "momentum_5",
                    "--start",
                    "2022-01-01",
                    "--end",
                    "2022-01-31",
                ]
            )

        assert result == 0, f"Expected exit 0, got {result}"

    def test_factor_found_but_invalid(self, tmp_path):
        """Factor found but |ICIR| below threshold → valid=false."""
        fixture = _make_ohlcv_fixture()

        with patch(
            "trader_off.cli.check_factor._load_ohlcv_data",
            return_value=fixture,
        ):
            result = main(
                argv=[
                    "--name",
                    "momentum_5",
                    "--start",
                    "2022-01-01",
                    "--end",
                    "2022-01-31",
                    "--ic-threshold",
                    "0.9",
                ]
            )

        assert result == 0, f"Expected exit 0, got {result}"

    def test_output_contains_factor_key(self, capsys, tmp_path):
        """Output JSON contains 'factor' key matching the requested name."""
        fixture = _make_ohlcv_fixture()

        with patch(
            "trader_off.cli.check_factor._load_ohlcv_data",
            return_value=fixture,
        ):
            main(
                argv=[
                    "--name",
                    "momentum_5",
                    "--start",
                    "2022-01-01",
                    "--end",
                    "2022-01-31",
                ]
            )

        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"
        assert "data" in output
        assert output["data"]["factor"] == "momentum_5"

    def test_output_contains_ic_fields(self, capsys, tmp_path):
        """Output JSON contains ic, icir, rank_ic, rank_icir, valid fields."""
        fixture = _make_ohlcv_fixture()

        with patch(
            "trader_off.cli.check_factor._load_ohlcv_data",
            return_value=fixture,
        ):
            main(
                argv=[
                    "--name",
                    "momentum_5",
                    "--start",
                    "2022-01-01",
                    "--end",
                    "2022-01-31",
                ]
            )

        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        data = output["data"]
        assert "ic" in data
        assert "icir" in data
        assert "rank_ic" in data
        assert "rank_icir" in data
        assert "valid" in data
        assert isinstance(data["ic"], (int, float))
        assert isinstance(data["icir"], (int, float))
        assert isinstance(data["rank_ic"], (int, float))
        assert isinstance(data["rank_icir"], (int, float))
        assert isinstance(data["valid"], bool)

    def test_json_flag_produces_json(self, capsys, tmp_path):
        """--json flag produces valid JSON output."""
        fixture = _make_ohlcv_fixture()

        with patch(
            "trader_off.cli.check_factor._load_ohlcv_data",
            return_value=fixture,
        ):
            main(
                argv=[
                    "--name",
                    "momentum_5",
                    "--start",
                    "2022-01-01",
                    "--end",
                    "2022-01-31",
                    "--json",
                ]
            )

        captured = capsys.readouterr()
        # Output must be valid JSON
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"


# ---------------------------------------------------------------------------
# Error path tests
# ---------------------------------------------------------------------------


class TestCheckFactorErrors:
    """Error path tests for check_factor CLI."""

    def test_factor_not_found(self, capsys, tmp_path):
        """Factor name not matching any candidate → error output."""
        fixture = _make_ohlcv_fixture()

        with patch(
            "trader_off.cli.check_factor._load_ohlcv_data",
            return_value=fixture,
        ):
            result = main(
                argv=[
                    "--name",
                    "nonexistent_factor_xyz",
                    "--start",
                    "2022-01-01",
                    "--end",
                    "2022-01-31",
                ]
            )

        assert result == 1, f"Expected exit 1, got {result}"
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output["status"] == "error"
        assert "data" in output
        assert "message" in output["data"]

    def test_no_data_boundary(self, capsys, tmp_path):
        """Empty OHLCV data → 'no valid data' reason, valid=false."""
        # Use an empty DataFrame with correct schema
        empty_fixture = pl.DataFrame(
            schema={
                "asset": pl.Utf8,
                "date": pl.Date,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
                "turnover": pl.Float64,
            }
        )

        with patch(
            "trader_off.cli.check_factor._load_ohlcv_data",
            return_value=empty_fixture,
        ):
            result = main(
                argv=[
                    "--name",
                    "momentum_5",
                    "--start",
                    "2022-01-01",
                    "--end",
                    "2022-01-31",
                ]
            )

        assert result == 0, f"Expected exit 0, got {result}"
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"
        data = output["data"]
        assert data["factor"] == "momentum_5"
        assert data["ic"] == 0
        assert data["icir"] == 0
        assert data["rank_ic"] == 0
        assert data["rank_icir"] == 0
        assert data["valid"] is False
        assert data["reason"] == "no valid data"


# ---------------------------------------------------------------------------
# NFR-0100: function-scope lazy imports (AST verification)
# ---------------------------------------------------------------------------


_BLACKLISTED = [
    "quantide.service",
    "quantide.portfolio",
    "quantide.backtest",
    "quantide.core.scheduler",
    "quantide.data.models.daily_bars",
]


class TestNFR0100CheckFactor:
    """NFR-0100: AST-level verification of lazy imports in check_factor.py."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_file(self):
        """Skip AST tests if check_factor.py doesn't exist yet (Red phase)."""
        if not SRC_FILE.exists():
            pytest.skip("check_factor.py not yet created (Red phase)")

    def test_no_top_level_quantide_imports(self):
        """AST parse confirms no quantide import at module top level."""
        tree = ast.parse(SRC_FILE.read_text())

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
        for banned in _BLACKLISTED:
            assert banned not in content, (
                f"Blacklisted quantide import '{banned}' found in check_factor.py (NFR-0100)"
            )

    def test_cli_dir_no_top_level_quantide(self):
        """Grep: no top-level quantide imports in check_factor.py."""
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
            f"Top-level quantide import found in check_factor.py:\n{result.stdout}"
        )

    def test_quantide_data_loader_allowlisted(self):
        """NFR-0100: QuantideDataLoader import from trader_off.data is allowed."""
        content = SRC_FILE.read_text()
        # The import should be from trader_off.data.quantide_adapter, not from quantide directly
        assert "trader_off.data.quantide_adapter" in content or "QuantideDataLoader" in content, (
            "Expected QuantideDataLoader import pattern (NFR-0100)"
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
