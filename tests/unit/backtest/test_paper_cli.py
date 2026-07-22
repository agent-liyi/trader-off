"""Tests for paper-trade CLI — FR-0200."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl

# ── CLI argument parsing tests ──────────────────────────────────────────────


class TestPaperTradeCLIArgs:
    """FR-0200: CLI argument parsing and defaults."""

    # AC-FR0200-02: --strategy is required, missing → exit 2
    def test_missing_strategy_exits_2(self):
        """CLI exits with code 2 when --strategy is missing."""
        from trader_off.cli.paper_trade import main

        with patch("trader_off.cli.paper_trade.run_paper_trade") as mock_run:
            mock_run.return_value = MagicMock(
                summary={"total_trades": 0},
                positions=pl.DataFrame(),
                trades=pl.DataFrame(),
                nav=pl.DataFrame(),
                report_dir=Path("/tmp"),
            )
            exit_code = main([])
        assert exit_code == 2, f"Expected exit code 2, got {exit_code}"

    # AC-FR0200-02: defaults for --end, --capital, --output
    def test_defaults_applied(self):
        """Verify default values: --end=today, --capital=1M, --output=reports/paper_trade_<ts>/."""
        from trader_off.cli.paper_trade import main

        with patch("trader_off.cli.paper_trade.run_paper_trade") as mock_run:
            mock_result = MagicMock()
            mock_result.summary = {"total_trades": 0}
            mock_result.positions = pl.DataFrame()
            mock_result.trades = pl.DataFrame()
            mock_result.nav = pl.DataFrame()
            mock_result.report_dir = Path("/tmp/reports")
            mock_run.return_value = mock_result

            exit_code = main(["--strategy", "optimized_topk"])

        assert exit_code == 0, f"Expected exit code 0, got {exit_code}"
        assert mock_run.called, "run_paper_trade must be called"
        kwargs = mock_run.call_args.kwargs
        assert kwargs["strategy_name"] == "optimized_topk"
        assert kwargs["end_date"] == date.today(), (
            f"end_date should default to today, got {kwargs['end_date']}"
        )
        assert kwargs["initial_cash"] == 1_000_000.0, (
            f"initial_cash should default to 1000000.0, got {kwargs['initial_cash']}"
        )

    # AC-FR0200-01: all args parsed correctly
    def test_all_args_parsed(self):
        """All CLI arguments are parsed and passed to run_paper_trade."""
        from trader_off.cli.paper_trade import main

        with patch("trader_off.cli.paper_trade.run_paper_trade") as mock_run:
            mock_result = MagicMock()
            mock_result.summary = {"total_trades": 5}
            mock_result.positions = pl.DataFrame({"asset": ["000001.SZ"]})
            mock_result.trades = pl.DataFrame({"action": ["buy"]})
            mock_result.nav = pl.DataFrame({"date": ["2026-07-21"], "nav": [1_000_000.0]})
            mock_result.report_dir = Path("/tmp/reports")
            mock_run.return_value = mock_result

            exit_code = main(
                [
                    "--strategy",
                    "optimized_topk",
                    "--end",
                    "2026-07-21",
                    "--capital",
                    "500000",
                    "--output",
                    "/tmp/paper_output",
                ]
            )

        assert exit_code == 0
        kwargs = mock_run.call_args.kwargs
        assert kwargs["strategy_name"] == "optimized_topk"
        assert kwargs["end_date"] == date(2026, 7, 21)
        assert kwargs["initial_cash"] == 500_000.0

    # --universe flag passes asset list to run_paper_trade via config
    def test_universe_flag_passes_assets(self, tmp_path):
        """--universe reads file and passes asset list in config."""
        from trader_off.cli.paper_trade import main

        # Create a universe CSV file
        universe_file = tmp_path / "watchlist.csv"
        universe_file.write_text("asset\n000001.SZ\n600519.SH\n")

        with patch("trader_off.cli.paper_trade.run_paper_trade") as mock_run:
            mock_result = MagicMock()
            mock_result.summary = {"total_trades": 0}
            mock_result.positions = pl.DataFrame()
            mock_result.trades = pl.DataFrame()
            mock_result.nav = pl.DataFrame()
            mock_result.report_dir = Path("/tmp/reports")
            mock_run.return_value = mock_result

            exit_code = main(["--strategy", "optimized_topk", "--universe", str(universe_file)])

        assert exit_code == 0
        kwargs = mock_run.call_args.kwargs
        config = kwargs.get("config") or {}
        universe = config.get("universe", [])
        assert set(universe) == {"000001.SZ", "600519.SH"}, (
            f"Expected universe from file, got {universe}"
        )

    # no --universe flag → empty universe passes (auto-derive in runner)
    def test_no_universe_flag_empty_config(self):
        """No --universe flag → empty universe list in config."""
        from trader_off.cli.paper_trade import main

        with patch("trader_off.cli.paper_trade.run_paper_trade") as mock_run:
            mock_result = MagicMock()
            mock_result.summary = {"total_trades": 0}
            mock_result.positions = pl.DataFrame()
            mock_result.trades = pl.DataFrame()
            mock_result.nav = pl.DataFrame()
            mock_result.report_dir = Path("/tmp/reports")
            mock_run.return_value = mock_result

            exit_code = main(["--strategy", "optimized_topk"])

        assert exit_code == 0
        kwargs = mock_run.call_args.kwargs
        config = kwargs.get("config") or {}
        universe = config.get("universe", [])
        assert universe == [], f"Expected empty universe, got {universe}"

    # AC-FR0200-06: exception → exit code 5
    def test_exception_exits_5(self):
        """CLI returns exit code 5 when run_paper_trade raises RuntimeError."""
        from trader_off.cli.paper_trade import main

        with patch("trader_off.cli.paper_trade.run_paper_trade") as mock_run:
            mock_run.side_effect = RuntimeError("paper engine down")

            exit_code = main(["--strategy", "optimized_topk"])

        assert exit_code == 5, f"Expected exit code 5, got {exit_code}"


# ── CLI output tests ────────────────────────────────────────────────────────


class TestPaperTradeCLIOutput:
    """FR-0200: CLI serializes output files."""

    # AC-FR0200-04: output files are written
    def test_output_files_written(self, tmp_path):
        """CLI writes summary.json, nav.parquet, positions.parquet, trades.parquet."""
        from trader_off.cli.paper_trade import main

        output_dir = tmp_path / "reports" / "paper_trade_test"
        output_dir.mkdir(parents=True, exist_ok=True)

        mock_result = MagicMock()
        mock_result.summary = {
            "annualized_return": 0.15,
            "sharpe_ratio": 1.2,
            "max_drawdown": -0.1,
            "win_rate": 0.55,
            "total_trades": 5,
            "avg_turnover": 0.03,
        }
        mock_result.positions = pl.DataFrame(
            {
                "date": ["2026-07-20", "2026-07-21"],
                "asset": ["000001.SZ", "600519.SH"],
                "weight": [0.5, 0.5],
            }
        )
        mock_result.trades = pl.DataFrame(
            {
                "date": ["2026-07-21"] * 5,
                "asset": ["000001.SZ"] * 5,
                "action": ["buy"] * 5,
                "quantity": [100.0] * 5,
            }
        )
        mock_result.nav = pl.DataFrame(
            {
                "date": ["2026-07-20", "2026-07-21", "2026-07-22"],
                "nav": [1_000_000.0, 1_005_000.0, 1_010_000.0],
            }
        )
        mock_result.report_dir = output_dir

        with patch("trader_off.cli.paper_trade.run_paper_trade") as mock_run:
            mock_run.return_value = mock_result

            exit_code = main(
                [
                    "--strategy",
                    "optimized_topk",
                    "--output",
                    str(output_dir),
                ]
            )

        assert exit_code == 0
        assert (output_dir / "summary.json").exists(), "summary.json not written"
        assert len(list(output_dir.glob("nav_*.parquet"))) > 0, "nav parquet not written"
        assert len(list(output_dir.glob("positions_*.parquet"))) > 0, (
            "positions parquet not written"
        )
        assert len(list(output_dir.glob("trades_*.parquet"))) > 0, "trades parquet not written"

        # Verify summary schema
        summary = json.loads((output_dir / "summary.json").read_text())
        required_6 = {
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "total_trades",
            "avg_turnover",
        }
        assert required_6.issubset(set(summary.keys()))

    # AC-FR0200-07: log output contains summary info
    def test_log_output_contains_summary_info(self):
        """CLI logs summary.json path and key metrics to stdout."""
        from trader_off.cli.paper_trade import main

        output_dir = Path("/tmp/reports/paper_trade_test")
        mock_result = MagicMock()
        mock_result.summary = {
            "total_trades": 5,
            "annualized_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "avg_turnover": 0.0,
        }
        mock_result.positions = pl.DataFrame()
        mock_result.trades = pl.DataFrame()
        mock_result.nav = pl.DataFrame({"date": ["2026-07-21"], "nav": [1_200_000.0]})
        mock_result.report_dir = output_dir

        with patch("trader_off.cli.paper_trade.run_paper_trade") as mock_run:
            mock_run.return_value = mock_result
            with patch("trader_off.cli.paper_trade.logger") as mock_logger:
                exit_code = main(["--strategy", "optimized_topk"])

        assert exit_code == 0
        # Verify logger.info was called
        assert mock_logger.info.called, "logger.info should be called on success"

    # AC-FR0200-05: --help exits 0 and prints argparse help
    def test_help_exits_zero(self):
        """--help outputs argparse help and exits with code 0."""
        from trader_off.cli.paper_trade import main

        exit_code = main(["--help"])
        assert exit_code == 0, f"Expected exit code 0, got {exit_code}"
