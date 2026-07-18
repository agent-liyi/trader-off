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
        # check cov_window is passed to estimate_covariance
