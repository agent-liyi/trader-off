"""Tests for CLI exit codes — FR-0600."""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from trader_off.backtest.runner import BacktestResult, run_backtest


class TestCLIExitCodes:
    """FR-0600: CLI exit code mapping."""

    # AC-FR0600-01: exit 0 on success
    def test_exit_zero_on_success(self):
        """CLI exits 0 when backtest succeeds."""
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

    # AC-FR0600-03: exit 2 on missing --capital
    def test_exit_two_missing_capital(self):
        """CLI exits 2 when --capital is missing (argparse error)."""
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
        ]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                backtest_main()
            assert exc_info.value.code == 2, f"Expected exit 2, got {exc_info.value.code}"

    # AC-FR0600-04: exit 4 on config validation failure
    def test_exit_four_config_validation_error(self):
        """CLI exits 4 when config validation fails."""
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
            "--config",
            "/nonexistent.yaml",
        ]
        with patch.object(sys, "argv", test_args):
            exit_code = backtest_main()
            assert exit_code == 4, f"Expected exit 4, got {exit_code}"

    # AC-FR0600-05: exit 5 on engine failure
    def test_exit_five_engine_failure(self):
        """CLI exits 5 when backtest engine fails."""
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
                mock_run.side_effect = RuntimeError("BacktestRunner failed: engine error")
                exit_code = backtest_main()
            assert exit_code == 5, f"Expected exit 5, got {exit_code}"


class TestSummarySchema:
    """FR-0600: extended summary.json schema."""

    # AC-FR0600-06: 6 required keys present
    def test_six_required_keys(self):
        """summary.json has 6 v0.1.0 required keys."""
        from quantide.data.models.daily_bars import daily_bars as real_daily_bars
        from quantide.data.sqlite import db as real_db

        with patch.object(real_daily_bars, "connect"):
            with patch.object(real_db, "init"):
                with patch.object(
                    real_db,
                    "assets_all",
                    return_value=pl.DataFrame(
                        {"dt": ["2023-01-03", "2023-01-04"], "total": [1000000.0, 1005000.0]}
                    ),
                ):
                    with patch.object(real_db, "positions_all", return_value=pl.DataFrame()):
                        with patch.object(real_db, "trades_all", return_value=pl.DataFrame()):
                            with patch("quantide.service.runner.BacktestRunner") as mock_runner_cls:
                                mock_runner = MagicMock()
                                mock_runner.run.return_value = {
                                    "portfolio_id": "test-schema",
                                    "metrics": {
                                        "annualized_return": 0.15,
                                        "sharpe_ratio": 1.2,
                                        "max_drawdown": -0.1,
                                        "win_rate": 0.55,
                                        "total_trades": 100,
                                        "avg_turnover": 0.03,
                                        "sortino": 1.8,
                                        "drawdown_duration_days": 15,
                                        "benchmark_return": 0.05,
                                    },
                                }
                                mock_runner_cls.return_value = mock_runner

                                result = run_backtest(
                                    model_version="v1",
                                    strategy_name="lgbm_top20",
                                    start=date(2023, 1, 1),
                                    end=date(2023, 12, 31),
                                    capital=1_000_000,
                                )

                                summary = result.summary
                                required_6 = {
                                    "annualized_return",
                                    "sharpe_ratio",
                                    "max_drawdown",
                                    "win_rate",
                                    "total_trades",
                                    "avg_turnover",
                                }
                                assert required_6.issubset(set(summary.keys()))

    # AC-FR0600-07: correct types
    def test_summary_types(self):
        """summary values have correct types."""
        required_floats = [
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "avg_turnover",
        ]
        for key in required_floats:
            assert isinstance(result_from_mock().get(key), float), f"{key} should be float"
        assert isinstance(result_from_mock().get("total_trades"), int)

    # AC-FR0600-08: optional keys present
    def test_optional_keys(self):
        """summary has optional extended keys from quantide."""
        from quantide.data.models.daily_bars import daily_bars as real_daily_bars
        from quantide.data.sqlite import db as real_db

        with patch.object(real_daily_bars, "connect"):
            with patch.object(real_db, "init"):
                with patch.object(
                    real_db,
                    "assets_all",
                    return_value=pl.DataFrame({"dt": ["2023-01-03"], "total": [1000000.0]}),
                ):
                    with patch.object(real_db, "positions_all", return_value=pl.DataFrame()):
                        with patch.object(real_db, "trades_all", return_value=pl.DataFrame()):
                            with patch("quantide.service.runner.BacktestRunner") as mock_runner_cls:
                                mock_runner = MagicMock()
                                mock_runner.run.return_value = {
                                    "portfolio_id": "test-opts",
                                    "metrics": {
                                        "annualized_return": 0.15,
                                        "sharpe_ratio": 1.2,
                                        "max_drawdown": -0.1,
                                        "win_rate": 0.55,
                                        "total_trades": 100,
                                        "avg_turnover": 0.03,
                                        "sortino": 1.8,
                                        "drawdown_duration_days": 15,
                                        "benchmark_return": 0.05,
                                    },
                                }
                                mock_runner_cls.return_value = mock_runner

                                result = run_backtest(
                                    model_version="v1",
                                    strategy_name="lgbm_top20",
                                    start=date(2023, 1, 1),
                                    end=date(2023, 12, 31),
                                    capital=1_000_000,
                                )

                                summary = result.summary
                                assert summary.get("sortino") == 1.8
                                assert summary.get("drawdown_duration_days") == 15
                                assert summary.get("benchmark_return") == 0.05


def result_from_mock(capital: float = 1_000_000) -> dict:
    """Helper to create a mock-backed run_backtest and return summary."""
    from quantide.data.models.daily_bars import daily_bars as real_daily_bars
    from quantide.data.sqlite import db as real_db

    with patch.object(real_daily_bars, "connect"):
        with patch.object(real_db, "init"):
            with patch.object(
                real_db,
                "assets_all",
                return_value=pl.DataFrame({"dt": ["2023-01-03"], "total": [capital]}),
            ):
                with patch.object(real_db, "positions_all", return_value=pl.DataFrame()):
                    with patch.object(real_db, "trades_all", return_value=pl.DataFrame()):
                        with patch("quantide.service.runner.BacktestRunner") as mock_runner_cls:
                            mock_runner = MagicMock()
                            mock_runner.run.return_value = {
                                "portfolio_id": "test-types",
                                "metrics": {
                                    "annualized_return": 0.1,
                                    "sharpe_ratio": 0.8,
                                    "max_drawdown": -0.05,
                                    "win_rate": 0.55,
                                    "total_trades": 50,
                                    "avg_turnover": 0.02,
                                },
                            }
                            mock_runner_cls.return_value = mock_runner

                            result = run_backtest(
                                model_version="v1",
                                strategy_name="lgbm_top20",
                                start=date(2023, 1, 1),
                                end=date(2023, 12, 31),
                                capital=capital,
                            )
                            return result.summary
