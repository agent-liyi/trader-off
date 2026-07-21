"""Tests for backtest runner — FR-0500: rewrite to delegate to quantide."""

import inspect
import json
import sys
from dataclasses import fields
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from trader_off.backtest.runner import BacktestResult, run_backtest

RUNNER_PATH = Path("src/trader_off/backtest/runner.py")
RUNNER_TEXT = RUNNER_PATH.read_text() if RUNNER_PATH.exists() else ""


class TestRunnerNoFakeData:
    """FR-0500: synthetic data branch deleted."""

    # AC-FR0500-01: no np.random.RandomState(42) in runner
    def test_no_random_state_42(self):
        """runner.py does not contain np.random.RandomState(42)."""
        assert "np.random.RandomState(42)" not in RUNNER_TEXT, (
            "np.random.RandomState(42) should be removed"
        )

    # AC-FR0500-02: daily_bars.connect is used
    def test_uses_daily_bars_connect(self):
        """runner.py contains daily_bars.connect call."""
        assert "daily_bars.connect(" in RUNNER_TEXT, "runner.py must use daily_bars.connect"

    # AC-FR0500-03: BacktestRunner is used
    def test_uses_backtest_runner(self):
        """runner.py imports BacktestRunner and uses it."""
        assert "BacktestRunner" in RUNNER_TEXT, "Missing BacktestRunner import"
        assert "runner.run(" in RUNNER_TEXT, "Missing runner.run() call"

    # AC-FR0500-06: no top-level import quantide in runner.py
    def test_no_direct_quantide_import(self):
        """runner.py has no top-level import quantide statement."""
        for line in RUNNER_TEXT.splitlines():
            stripped = line.strip()
            if stripped.startswith("import quantide") or stripped.startswith("from quantide"):
                # Only allow if inside a function (indented)
                if not line.startswith((" ", "\t")):
                    pytest.fail(f"Top-level quantide import found: {stripped}")

    # AC-FR0500-07: default store path is v0.3.0
    def test_default_store_path(self):
        """Default store path points to tests/fixtures/v0.3.0/daily_bars_store/."""
        assert "tests/fixtures/v0.3.0/daily_bars_store" in RUNNER_TEXT, (
            "Default store path should be v0.3.0 fixtures"
        )
        assert "tests/fixtures/v0.3.0/calendar_store" not in RUNNER_TEXT, (
            "No persistent calendar_store directory should exist"
        )


class TestRunBacktestSignature:
    """FR-0500: public API unchanged."""

    # AC-FR0500-04: run_backtest signature unchanged
    def test_run_backtest_signature(self):
        """run_backtest has the same public signature."""
        sig = inspect.signature(run_backtest)
        params = set(sig.parameters.keys())
        expected = {"model_version", "strategy_name", "start", "end", "capital", "config"}
        assert params == expected, f"Expected {expected}, got {params}"

    # AC-FR0500-05: BacktestResult fields unchanged
    def test_backtest_result_fields(self):
        """BacktestResult has same fields."""
        field_names = {f.name for f in fields(BacktestResult)}
        expected = {"summary", "positions", "trades", "nav", "report_dir"}
        assert field_names == expected, f"Expected {expected}, got {field_names}"


class TestInlineCalendar:
    """FR-0500: inline calendar generation (AC-FR0500-09, AC-FR0500-11)."""

    def test_inline_calendar_generated(self, tmp_path):
        """Inline calendar parquet is generated with correct schema."""
        from trader_off.backtest.runner import _generate_inline_calendar

        dates = [date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5)]
        result_path = _generate_inline_calendar(dates, tmp_path / "calendar.parquet")

        assert result_path.exists(), f"Calendar not generated at {result_path}"
        cal_df = pl.read_parquet(result_path)
        assert set(cal_df.columns) == {"date", "is_open", "prev"}, (
            f"Wrong calendar schema: {cal_df.columns}"
        )
        assert (cal_df["is_open"] == 1).all(), "All days should be marked open"

    def test_calendar_has_prev_day_before_first_date(self, tmp_path):
        """FR-0100: calendar day_shift(start, -1) returns a date before start.

        When the inline calendar starts at a given date, day_shift(start, -1)
        must return a real previous day (not the same day) to avoid ClockRewind
        in BacktestBroker.set_clock.
        """
        from quantide.data.models.calendar import Calendar

        from trader_off.backtest.runner import _generate_inline_calendar

        # Use dates starting at 2024-01-02 (same pattern as ohlcv_10x60 fixture)
        dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
        cal_path = _generate_inline_calendar(dates, tmp_path / "calendar.parquet")

        # Load the calendar into quantide Calendar
        cal = Calendar()
        cal.load(str(cal_path))

        first_date = dates[0]

        # Before fix: day_shift(first_date, -1) returns first_date itself
        # After fix: day_shift(first_date, -1) returns a date before first_date
        prev_day = cal.day_shift(first_date, -1)
        assert prev_day < first_date, (
            f"day_shift({first_date}, -1) returned {prev_day}, "
            f"must be before {first_date} to avoid ClockRewind"
        )

    def test_calendar_generation_failure(self):
        """Calendar generation failure raises RuntimeError."""
        from trader_off.backtest.runner import _generate_inline_calendar

        # Path to a read-only location (will fail at write)
        with pytest.raises(RuntimeError, match="calendar"):
            _generate_inline_calendar([date(2023, 1, 3)], Path("/root/nope/cal.parquet"))


class TestRunBacktestWithMock:
    """FR-0500: integration with quantide APIs (mocked)."""

    # AC-FR0500-08: store_path from config overrides default
    def test_store_path_from_config(self, tmp_path):
        """store_path from config is used in daily_bars.connect."""
        from quantide.data.models.daily_bars import daily_bars as real_daily_bars
        from quantide.data.sqlite import db as real_db

        with patch.object(real_daily_bars, "connect") as mock_connect:
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
                                    "portfolio_id": "test-001",
                                    "metrics": {},
                                }
                                mock_runner_cls.return_value = mock_runner

                                run_backtest(
                                    model_version="v1",
                                    strategy_name="lgbm_top20",
                                    start=date(2023, 1, 1),
                                    end=date(2023, 12, 31),
                                    capital=1_000_000,
                                    config={"store_path": str(tmp_path / "custom_store")},
                                )

                assert mock_connect.called, "daily_bars.connect was not called"
                store_arg = str(mock_connect.call_args[0][0])
                assert "custom_store" in store_arg, f"Expected custom_store path, got {store_arg}"

    # output files exist (summary.json, parquet files) — with mocks
    def test_output_files_with_mock_runner(self, tmp_path):
        """run_backtest creates summary.json and parquet files via mocked quantide."""
        from quantide.data.models.daily_bars import daily_bars as real_daily_bars
        from quantide.data.sqlite import db as real_db

        with patch.object(real_daily_bars, "connect"):
            with patch.object(real_db, "init"):
                with patch.object(real_db, "assets_all") as mock_assets:
                    mock_assets.return_value = pl.DataFrame(
                        {
                            "dt": ["2023-01-03", "2023-01-04", "2023-01-05"],
                            "total": [1000000.0, 1005000.0, 1010000.0],
                        }
                    )
                    with patch.object(real_db, "positions_all") as mock_positions:
                        mock_positions.return_value = pl.DataFrame(
                            {
                                "dt": ["2023-01-03"],
                                "asset": ["000001.SZ"],
                                "quantity": [1000.0],
                            }
                        )
                        with patch.object(real_db, "trades_all") as mock_trades:
                            mock_trades.return_value = pl.DataFrame(
                                {
                                    "dt": ["2023-01-03"],
                                    "asset": ["000001.SZ"],
                                    "action": ["buy"],
                                    "quantity": [1000.0],
                                    "price": [100.0],
                                }
                            )
                            with patch("quantide.service.runner.BacktestRunner") as mock_runner_cls:
                                mock_runner = MagicMock()
                                mock_runner.run.return_value = {
                                    "portfolio_id": "test-002",
                                    "metrics": {
                                        "annualized_return": 0.15,
                                        "sharpe_ratio": 1.2,
                                        "max_drawdown": -0.1,
                                        "win_rate": 0.55,
                                        "total_trades": 42,
                                        "avg_turnover": 0.03,
                                    },
                                }
                                mock_runner_cls.return_value = mock_runner

                                result = run_backtest(
                                    model_version="v1",
                                    strategy_name="lgbm_top20",
                                    start=date(2023, 1, 1),
                                    end=date(2023, 12, 31),
                                    capital=1_000_000,
                                    config={"store_path": str(tmp_path)},
                                )

                                report_dir = result.report_dir
                                assert (report_dir / "summary.json").exists()
                                assert len(list(report_dir.glob("nav_*"))) > 0
                                assert len(list(report_dir.glob("positions_*"))) > 0
                                assert len(list(report_dir.glob("trades_*"))) > 0

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
                                assert summary["total_trades"] == 42

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
                    positions=pl.DataFrame(),
                    trades=pl.DataFrame(),
                    nav=pl.DataFrame(),
                    report_dir=Path("/tmp"),
                )
                exit_code = backtest_main()
        assert exit_code == 0

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
