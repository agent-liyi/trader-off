"""Tests for stock_list CLI — FR-0200.

Covers: argparse exit 2, happy path JSON output with --exchange/--status filter,
function-scope lazy import, always-JSON output.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# Will fail until stock_list.py is created (Red phase)
from trader_off.cli.stock_list import main  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_stock_df() -> pd.DataFrame:
    """Create a mock stock list DataFrame matching fetch_stock_list output."""
    return pd.DataFrame(
        {
            "asset": ["000001.SZ", "000002.SZ", "600000.SH", "600001.SH"],
            "name": ["平安银行", "万科A", "浦发银行", "邯郸钢铁"],
            "pinyin": ["PAYH", "WKAG", "PFYH", "HDGT"],
            "list_date": [
                pd.Timestamp("1991-04-03").date(),
                pd.Timestamp("1991-01-29").date(),
                pd.Timestamp("1999-11-10").date(),
                pd.Timestamp("1998-01-22").date(),
            ],
            "delist_date": [
                None,
                None,
                None,
                None,
            ],
        }
    )


# ---------------------------------------------------------------------------
# Exit code 2: Argparse errors
# ---------------------------------------------------------------------------


class TestArgparseExit2:
    """FR-0200: argparse failures → exit code 2."""

    def test_unknown_arg_exits_2(self):
        """Unknown flag → SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--unknown"])
        assert exc_info.value.code == 2

    def test_invalid_exchange(self, mock_stock_df):
        """Invalid --exchange value → should still be accepted by argparse
        (filtering is done downstream). Test that it doesn't crash."""
        with patch(
            "quantide.data.fetchers.tushare.fetch_stock_list",
            return_value=mock_stock_df,
        ):
            exit_code = main(["--exchange", "INVALID"])
        assert exit_code == 0

    def test_invalid_status(self, mock_stock_df):
        """Invalid --status value → accepted by argparse, filtered downstream."""
        with patch(
            "quantide.data.fetchers.tushare.fetch_stock_list",
            return_value=mock_stock_df,
        ):
            exit_code = main(["--status", "X"])
        assert exit_code == 0


# ---------------------------------------------------------------------------
# Happy path: JSON output + exit 0
# ---------------------------------------------------------------------------


class TestHappyPath:
    """FR-0200: fetch_stock_list → JSON output, exit 0."""

    @pytest.fixture
    def mock_fetch(self, mock_stock_df):
        """Mock fetch_stock_list to return a known DataFrame."""
        with patch(
            "quantide.data.fetchers.tushare.fetch_stock_list",
            return_value=mock_stock_df,
        ) as mock:
            yield mock

    def test_no_args_outputs_json(self, mock_fetch, capsys):
        """No args — full list JSON output."""
        exit_code = main([])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert "status" in output
        assert output["status"] == "ok"
        assert "data" in output
        assert "count" in output["data"]
        assert "stocks" in output["data"]
        mock_fetch.assert_called_once()

    def test_exchange_filter_sse(self, mock_fetch, capsys):
        """--exchange SSE filters to Shanghai stocks only."""
        exit_code = main(["--exchange", "SSE"])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["exchange"] == "SSE"
        stocks = output["data"]["stocks"]
        assert all(s["ts_code"].startswith("6") for s in stocks)

    def test_exchange_filter_szse(self, mock_fetch, capsys):
        """--exchange SZSE filters to Shenzhen stocks only."""
        exit_code = main(["--exchange", "SZSE"])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["exchange"] == "SZSE"
        stocks = output["data"]["stocks"]
        assert all(s["ts_code"].startswith(("0", "3")) for s in stocks)

    def test_exchange_filter_bse(self, mock_fetch, capsys):
        """--exchange BSE filters to Beijing stocks."""
        exit_code = main(["--exchange", "BSE"])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["exchange"] == "BSE"

    def test_status_filter(self, mock_fetch, capsys):
        """--status L filters to listed stocks."""
        exit_code = main(["--status", "L"])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["status"] == "L"

    def test_json_flag_always_json(self, mock_fetch, capsys):
        """--json flag still produces JSON output."""
        exit_code = main(["--json"])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["status"] == "ok"

    def test_combined_filters(self, mock_fetch, capsys):
        """Combine --exchange and --status."""
        exit_code = main(["--exchange", "SSE", "--status", "L"])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        assert output["data"]["exchange"] == "SSE"
        assert output["data"]["status"] == "L"

    def test_stock_entry_format(self, mock_fetch, capsys):
        """Each stock entry has ts_code and name fields."""
        exit_code = main([])
        captured = capsys.readouterr()

        assert exit_code == 0
        output = json.loads(captured.out.strip())
        for stock in output["data"]["stocks"]:
            assert "ts_code" in stock
            assert "name" in stock


# ---------------------------------------------------------------------------
# Function-scope lazy import
# ---------------------------------------------------------------------------


class TestLazyImport:
    """FR-0200 / NFR-0100: quantide imports are function-scope only."""

    def test_no_quantide_import_at_module_level(self):
        """Module-level does NOT import quantide eagerly."""
        import ast

        source = Path("src/trader_off/cli/stock_list.py").read_text()
        tree = ast.parse(source)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("quantide"), (
                        f"Module-level import of quantide found: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                assert node.module is None or not node.module.startswith("quantide"), (
                    f"Module-level import of quantide found: {node.module}"
                )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """FR-0200: edge cases for stock-list CLI."""

    @pytest.fixture
    def mock_fetch_empty(self):
        """Mock fetch_stock_list returning None (no data)."""
        with patch(
            "quantide.data.fetchers.tushare.fetch_stock_list",
            return_value=None,
        ) as mock:
            yield mock

    @pytest.fixture
    def mock_fetch_empty_df(self):
        """Mock fetch_stock_list returning empty DataFrame."""
        with patch(
            "quantide.data.fetchers.tushare.fetch_stock_list",
            return_value=pd.DataFrame(),
        ) as mock:
            yield mock

    def test_empty_result_handled(self, mock_fetch_empty, capsys):
        """None result → error status, exit 1."""
        exit_code = main([])
        captured = capsys.readouterr()

        assert exit_code == 1
        output = json.loads(captured.out.strip())
        assert output["status"] == "error"

    def test_main_returns_int(self):
        """main() return type is int."""
        with patch(
            "quantide.data.fetchers.tushare.fetch_stock_list",
            return_value=pd.DataFrame({"asset": [], "name": []}),
        ):
            result = main([])
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


class TestEntryPoint:
    """FR-0200: module-level entry point works."""

    def test_main_is_callable(self):
        """Smoke: import succeeds and main is callable."""
        with patch(
            "quantide.data.fetchers.tushare.fetch_stock_list",
            return_value=pd.DataFrame({"asset": ["000001.SZ"], "name": ["平安银行"]}),
        ):
            result = main([])
        assert isinstance(result, int)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
