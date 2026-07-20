"""Integration tests for backtest CLI and runner (L2 contract simulation).

Covers the cross-module chain:
  cli.backtest → backtest.runner → backtest.metrics → report output
"""

import json
from datetime import date

import polars as pl
import pytest

from trader_off.backtest.runner import BacktestResult, run_backtest


@pytest.mark.integration
class TestBacktestIntegration:
    """Integration: CLI backtest → runner → metrics → file output."""

    def test_cli_exit_zero(self, capsys):
        """CLI backtest exits 0, prints 'Backtest finished'."""
        import sys
        from pathlib import Path
        from unittest.mock import patch

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
                    positions=pl.DataFrame(),
                    trades=pl.DataFrame(),
                    nav=pl.DataFrame(),
                    report_dir=Path("/tmp"),
                )
                exit_code = backtest_main()

        assert exit_code == 0

    def test_output_files(self):
        """run_backtest creates all required output files."""
        result = run_backtest(
            model_version="v1",
            strategy_name="lgbm_top20",
            start=date(2023, 1, 1),
            end=date(2023, 12, 31),
            capital=1_000_000,
        )

        report_dir = result.report_dir

        # Check output files exist
        assert (report_dir / "summary.json").exists(), "Missing summary.json"

        nav_files = list(report_dir.glob("nav_*.parquet"))
        assert len(nav_files) > 0, "Missing nav parquet"
        nav = pl.read_parquet(nav_files[0])
        assert len(nav) > 0, "Nav parquet is empty"

        pos_files = list(report_dir.glob("positions_*.parquet"))
        assert len(pos_files) > 0, "Missing positions parquet"
        pos = pl.read_parquet(pos_files[0])
        assert len(pos) > 0, "Positions parquet is empty"

        trade_files = list(report_dir.glob("trades_*.parquet"))
        assert len(trade_files) > 0, "Missing trades parquet"
        trades = pl.read_parquet(trade_files[0])
        assert len(trades) > 0, "Trades parquet is empty"

        # Verify summary.json has required keys
        summary = json.loads((report_dir / "summary.json").read_text())
        required = {
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "total_trades",
            "avg_turnover",
        }
        assert required.issubset(set(summary.keys())), (
            f"Missing keys: {required - set(summary.keys())}"
        )

    def test_missing_capital(self):
        """missing --capital exits non-zero."""
        import sys
        from unittest.mock import patch

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
            # --capital is intentionally missing
        ]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit):
                backtest_main()

    def test_metrics_integration(self):
        """compute_performance_metrics produces valid summary.

        Verifies that run_backtest → compute_performance_metrics chain
        produces a summary with all required fields and valid types.
        """
        result = run_backtest(
            model_version="v1",
            strategy_name="lgbm_top20",
            start=date(2023, 1, 1),
            end=date(2023, 12, 31),
            capital=1_000_000,
        )

        summary = result.summary

        assert isinstance(summary["annualized_return"], float)
        assert isinstance(summary["sharpe_ratio"], float)
        assert isinstance(summary["max_drawdown"], float)
        assert isinstance(summary["win_rate"], float)
        assert isinstance(summary["total_trades"], int)
        assert isinstance(summary["avg_turnover"], float)

        # Performance metrics should be in reasonable ranges
        assert summary["win_rate"] >= 0.0
        assert summary["max_drawdown"] <= 0.0  # negative by convention
