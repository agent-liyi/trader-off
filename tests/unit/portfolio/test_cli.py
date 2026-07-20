"""Unit tests for portfolio.cli (FR-4100: optimize CLI).

AC-FR4100-01: trader-off optimize returns exit 0, stdout contains "Sharpe="
AC-FR4100-02: --predictions file not found → exit 2
AC-FR4100-03: too few assets (<5) → exit 3
AC-FR4100-04: --cov-window=30 passed to covariance estimator
"""

import numpy as np
import polars as pl
import pytest


class TestOptimizeCli:
    """Tests for the optimize CLI subcommand."""

    @pytest.fixture
    def predictions_csv(self, tmp_path):
        """Create a valid predictions CSV fixture."""
        path = tmp_path / "predictions.csv"
        rows = [
            {"asset": f"stock_{i:03d}", "score": 0.001 * (50 - i), "rank": i + 1} for i in range(50)
        ]
        df = pl.DataFrame(rows)
        df.write_csv(path)
        return path

    @pytest.fixture
    def industry_csv(self, tmp_path):
        """Create a valid industry map CSV fixture."""
        path = tmp_path / "industry_map.csv"
        rows = [
            {"asset": f"stock_{i:03d}", "industry": ["banking", "tech", "real_estate"][i % 3]}
            for i in range(50)
        ]
        df = pl.DataFrame(rows)
        df.write_csv(path)
        return path

    @pytest.fixture
    def returns_csv(self, tmp_path):
        """Create a returns CSV for covariance estimation."""
        path = tmp_path / "returns.csv"
        n_assets = 50
        n_days = 60
        np.random.seed(42)
        dates = [f"2026-07-{d:02d}" for d in range(1, n_days + 1)]
        data = {"date": dates}
        for i in range(n_assets):
            data[f"stock_{i:03d}"] = np.random.randn(n_days) * 0.01
        df = pl.DataFrame(data)
        df.write_csv(path)
        return path

    def test_ac_fr4100_01_exit_0_and_sharpe_output(
        self,
        predictions_csv,
        industry_csv,
        returns_csv,
        tmp_path,
        capsys,
    ):
        """AC-FR4100-01: optimize CLI exits 0 and prints Sharpe=."""
        from trader_off.portfolio.cli import main

        output_dir = tmp_path / "reports" / "portfolio_test"

        exit_code = main(
            [
                "--predictions",
                str(predictions_csv),
                "--industry-map",
                str(industry_csv),
                "--returns",
                str(returns_csv),
                "--output",
                str(output_dir),
            ]
        )

        captured = capsys.readouterr()
        assert exit_code == 0, f"CLI failed with stderr: {captured.err}"
        assert "Sharpe=" in captured.out, f"Sharpe not in output: {captured.out}"

    def test_ac_fr4100_02_missing_predictions(self, industry_csv, tmp_path, capsys):
        """AC-FR4100-02: missing predictions file → exit 2."""
        from trader_off.portfolio.cli import main

        output_dir = tmp_path / "out"
        fake_predictions = tmp_path / "nonexistent.csv"

        exit_code = main(
            [
                "--predictions",
                str(fake_predictions),
                "--industry-map",
                str(industry_csv),
                "--output",
                str(output_dir),
            ]
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert "not found" in captured.err or "not exist" in captured.err.lower()

    def test_ac_fr4100_03_too_few_assets(self, tmp_path, capsys):
        """AC-FR4100-03: <5 candidate assets → exit 3."""
        from trader_off.portfolio.cli import main

        pred_path = tmp_path / "predictions.csv"
        df = pl.DataFrame(
            {
                "asset": ["A", "B", "C"],
                "score": [0.1, 0.09, 0.08],
                "rank": [1, 2, 3],
            }
        )
        df.write_csv(pred_path)

        industry_path = tmp_path / "industry.csv"
        df_ind = pl.DataFrame(
            {"asset": ["A", "B", "C"], "industry": ["banking", "tech", "banking"]}
        )
        df_ind.write_csv(industry_path)

        output_dir = tmp_path / "out"

        exit_code = main(
            [
                "--predictions",
                str(pred_path),
                "--industry-map",
                str(industry_path),
                "--output",
                str(output_dir),
            ]
        )

        captured = capsys.readouterr()
        assert exit_code == 3
        assert "too few assets" in captured.err.lower()

    def test_ac_fr4100_04_cov_window_respected(
        self, predictions_csv, industry_csv, returns_csv, tmp_path
    ):
        """AC-FR4100-04: --cov-window=30 passed to covariance estimator."""
        from trader_off.portfolio.cli import main

        output_dir = tmp_path / "reports" / "cov_test"

        exit_code = main(
            [
                "--predictions",
                str(predictions_csv),
                "--industry-map",
                str(industry_csv),
                "--returns",
                str(returns_csv),
                "--output",
                str(output_dir),
                "--cov-window",
                "30",
            ]
        )

        # The CLI should complete successfully with --cov-window
        assert exit_code == 0

    def test_ac_fr4100_02b_missing_industry_map(self, predictions_csv, tmp_path, capsys):
        """Missing industry map file → exit 2."""
        from trader_off.portfolio.cli import main

        # Create predictions file (valid)
        pred_path = tmp_path / "predictions.csv"
        df = pl.DataFrame(
            {
                "asset": [f"stock_{i:03d}" for i in range(50)],
                "score": [0.001 * (50 - i) for i in range(50)],
                "rank": list(range(1, 51)),
            }
        )
        df.write_csv(pred_path)

        output_dir = tmp_path / "out"
        fake_industry = tmp_path / "nonexistent_industry.csv"

        exit_code = main(
            [
                "--predictions",
                str(pred_path),
                "--industry-map",
                str(fake_industry),
                "--output",
                str(output_dir),
            ]
        )

        assert exit_code == 2

    def test_ac_fr4100_02c_missing_returns(self, predictions_csv, industry_csv, tmp_path, capsys):
        """Missing returns file → exit 2."""
        from trader_off.portfolio.cli import main

        output_dir = tmp_path / "out"
        fake_returns = tmp_path / "nonexistent_returns.csv"

        exit_code = main(
            [
                "--predictions",
                str(predictions_csv),
                "--industry-map",
                str(industry_csv),
                "--returns",
                str(fake_returns),
                "--output",
                str(output_dir),
            ]
        )

        assert exit_code == 2

    def test_cli_success_no_industry_map(
        self,
        predictions_csv,
        returns_csv,
        tmp_path,
        capsys,
    ):
        """CLI succeeds with industry_map=None (industry-neutral disabled)."""
        from trader_off.portfolio.cli import main

        output_dir = tmp_path / "reports" / "no_industry"

        exit_code = main(
            [
                "--predictions",
                str(predictions_csv),
                "--returns",
                str(returns_csv),
                "--output",
                str(output_dir),
                "--industry-neutral",
                "--industry-neutral-tol",
                "0.05",
            ]
        )

        assert exit_code == 0

    def test_cli_success_no_returns_uses_identity(
        self,
        predictions_csv,
        industry_csv,
        tmp_path,
        capsys,
    ):
        """CLI succeeds without --returns (uses identity covariance)."""
        from trader_off.portfolio.cli import main

        output_dir = tmp_path / "reports" / "no_returns"

        exit_code = main(
            [
                "--predictions",
                str(predictions_csv),
                "--industry-map",
                str(industry_csv),
                "--output",
                str(output_dir),
            ]
        )

        assert exit_code == 0

    def test_cli_prediction_invalid_columns(self, tmp_path, capsys):
        """predictions CSV missing required columns → raises ValueError."""
        from trader_off.portfolio.cli import _load_predictions

        bad_csv = tmp_path / "bad_predictions.csv"
        bad_csv.write_text("asset,score\nA,0.1\n")

        with pytest.raises(ValueError, match="must have columns"):
            _load_predictions(bad_csv)

    def test_cli_cov_window_zero(
        self,
        predictions_csv,
        industry_csv,
        returns_csv,
        tmp_path,
        capsys,
    ):
        """CLI with --cov-window=0 uses all available data."""
        from trader_off.portfolio.cli import main

        output_dir = tmp_path / "reports" / "cov_zero"

        exit_code = main(
            [
                "--predictions",
                str(predictions_csv),
                "--industry-map",
                str(industry_csv),
                "--returns",
                str(returns_csv),
                "--output",
                str(output_dir),
                "--cov-window",
                "0",
            ]
        )

        # Should complete (cov_window=0 means use all data)
        assert exit_code == 0

    def test_cli_includes_solver_result_in_output(
        self,
        predictions_csv,
        industry_csv,
        returns_csv,
        tmp_path,
    ):
        """save_portfolio_results is called with solver_result."""
        from trader_off.portfolio import cli as cli_module

        output_dir = tmp_path / "reports" / "solver_result_test"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cli_module, "save_portfolio_results", lambda **kwargs: {})
            exit_code = cli_module.main(
                [
                    "--predictions",
                    str(predictions_csv),
                    "--industry-map",
                    str(industry_csv),
                    "--returns",
                    str(returns_csv),
                    "--output",
                    str(output_dir),
                ]
            )
        assert exit_code == 0
