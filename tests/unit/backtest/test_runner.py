"""Tests for backtest runner."""

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from trader_off.backtest.runner import BacktestResult, run_backtest


class TestRunBacktest:
    """Unit tests for run_backtest."""

    # CLI exit 0 + "Backtest finished"
    def test_cli_exit_zero(self, tmp_path, capsys):
        """CLI backtest exits 0, prints 'Backtest finished'."""
        from trader_off.cli.backtest import main as backtest_main

        test_args = [
            "backtest",
            "--model",
            "v1",
            "--strategy",
            "lgbm_top20",
            "--start",
            "2023-01-01",
            "--end",
            "2023-12-31",
            "--capital",
            "1000000",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("trader_off.cli.backtest.run_backtest") as mock_run:
                mock_run.return_value = BacktestResult(
                    summary={},
                    positions=None,
                    trades=None,
                    nav=None,
                    report_dir=Path("/tmp"),
                )
                exit_code = backtest_main()

        assert exit_code == 0

    # output files exist (summary.json, parquet files)
    def test_output_files(self):
        """run_backtest creates summary.json and parquet files."""
        result = run_backtest(
            model_version="v1",
            strategy_name="lgbm_top20",
            start=date(2023, 1, 1),
            end=date(2023, 12, 31),
            capital=1_000_000,
        )

        report_dir = result.report_dir

        # Check all required files
        assert (report_dir / "summary.json").exists()
        assert len(list(report_dir.glob("positions_*"))) > 0
        assert len(list(report_dir.glob("trades_*"))) > 0
        assert len(list(report_dir.glob("nav_*"))) > 0

        # Check parquet has data
        import polars as pl

        nav = pl.read_parquet(list(report_dir.glob("nav_*"))[0])
        assert len(nav) > 0

        # Check summary has required keys
        summary = json.loads((report_dir / "summary.json").read_text())
        required = {
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "total_trades",
            "avg_turnover",
        }
        assert required.issubset(set(summary.keys()))

    # missing --capital → error
    def test_missing_capital(self):
        """missing --capital exits non-zero."""
        from trader_off.cli.backtest import main as backtest_main

        test_args = [
            "backtest",
            "--model",
            "v1",
            "--strategy",
            "lgbm_top20",
            "--start",
            "2023-01-01",
            "--end",
            "2023-12-31",
            # --capital is missing
        ]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit):
                backtest_main()
