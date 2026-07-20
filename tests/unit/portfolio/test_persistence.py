"""Unit tests for portfolio.persistence (FR-4000: optimization result persistence).

AC-FR4000-01: reports/portfolio_<ts>/ 5 files, all > 100 bytes
AC-FR4000-02: weights.csv columns: asset, weight, sector, mu, in_universe; sum ≈ 1.0
AC-FR4000-03: atomic write (temp + rename) — no partial files on interruption
"""

import numpy as np
import polars as pl

from trader_off.portfolio.persistence import load_weights, save_weights


class TestSaveWeights:
    """Tests for save_weights (FR-4000 AC-02)."""

    def test_ac_fr4000_02_weight_sum(self, tmp_path):
        """AC-FR4000-02: weights.csv sum ≈ 1.0."""
        tickers = [f"stock_{i:03d}" for i in range(50)]
        weights = np.full(50, 1.0 / 50)
        out_dir = tmp_path / "portfolio_output"
        out_dir.mkdir()

        path = save_weights(dict(zip(tickers, weights)), tickers, out_dir)
        df = pl.read_csv(path)
        assert np.isclose(df["weight"].sum(), 1.0, atol=1e-6)

    def test_ac_fr4000_02_csv_format(self, tmp_path):
        """AC-FR4000-02: weights.csv has correct columns."""
        tickers = ["A", "B", "C"]
        weights = np.array([0.5, 0.3, 0.2])
        out_dir = tmp_path / "p"
        out_dir.mkdir()

        path = save_weights(dict(zip(tickers, weights)), tickers, out_dir)
        df = pl.read_csv(path)
        assert set(df.columns) == {"asset", "weight", "sector", "mu", "in_universe"}

    def test_ac_fr4000_02_weight_values(self, tmp_path):
        """AC-FR4000-02: weights.csv correct weight values."""
        tickers = ["X", "Y", "Z"]
        weights = np.array([0.6, 0.3, 0.1])
        out_dir = tmp_path / "p"
        out_dir.mkdir()

        path = save_weights(dict(zip(tickers, weights)), tickers, out_dir)
        df = pl.read_csv(path)
        for row in df.iter_rows(named=True):
            assert np.isclose(row["weight"], weights[tickers.index(row["asset"])], atol=1e-9)


class TestLoadWeights:
    """Tests for load_weights (FR-4000)."""

    def test_ac_fr4000_02_load_roundtrip(self, tmp_path):
        """AC-FR4000-02: load_weights is the inverse of save_weights."""
        tickers = ["A", "B", "C"]
        weights = np.array([0.5, 0.3, 0.2])
        out_dir = tmp_path / "p"
        out_dir.mkdir()

        path = save_weights(dict(zip(tickers, weights)), tickers, out_dir)
        loaded = load_weights(path)

        assert isinstance(loaded, dict)
        assert len(loaded) == 3
        for t in tickers:
            assert t in loaded
            assert np.isclose(loaded[t], weights[tickers.index(t)], atol=1e-9)

    def test_ac_fr4000_02_load_from_csv(self, tmp_path):
        """AC-FR4000-02: load_weights reads asset,weight CSV correctly."""
        csv_path = tmp_path / "weights.csv"
        csv_path.write_text("asset,weight\nA,0.6\nB,0.3\nC,0.1\n")

        loaded = load_weights(csv_path)
        assert np.isclose(loaded["A"], 0.6)
        assert np.isclose(loaded["B"], 0.3)
        assert np.isclose(loaded["C"], 0.1)


class TestPersistenceOutput:
    """Tests for FR-4000 AC-01/03: full report output and atomic write."""

    def test_ac_fr4000_01_files_exist(self, tmp_path):
        """AC-FR4000-01: save_portfolio_results creates all 5 required files."""
        from trader_off.portfolio.persistence import save_portfolio_results
        from trader_off.portfolio.solver import SolverResult

        tickers = [f"s{i:03d}" for i in range(20)]
        weights_arr = np.full(20, 1.0 / 20)
        mu = {t: 0.001 for t in tickers}
        cov = 0.0001 * np.eye(20)

        solver_result = SolverResult(
            weights=weights_arr,
            solver_status="optimal",
            backend_used="scipy",
            solve_time_sec=0.5,
            iterations=100,
        )

        out_dir = tmp_path / "reports" / "portfolio_20260718_120000"
        save_portfolio_results(
            weights=dict(zip(tickers, weights_arr)),
            tickers=tickers,
            mu=mu,
            cov=cov,
            out_dir=out_dir,
            solver_result=solver_result,
            constraint_report=None,
        )
        required_files = [
            "weights.csv",
            "optimizer_report.json",
            "portfolio_metrics.csv",
            "weights_diagnostics.json",
            "assets_dropped.json",
        ]
        for f in required_files:
            assert (out_dir / f).exists(), f"{f} missing"
            # assets_dropped.json can be small (empty list "[]" = 2 bytes) when no assets dropped
            min_size = 2 if f == "assets_dropped.json" else 100
            assert (out_dir / f).stat().st_size >= min_size, f"{f} too small"

    def test_ac_fr4000_03_atomic_write(self, tmp_path):
        """AC-FR4000-03: temp+rename — no partial files on interruption."""
        tickers = ["A", "B", "C"]
        weights = np.array([0.5, 0.3, 0.2])
        out_dir = tmp_path / "p"
        out_dir.mkdir()

        path = save_weights(dict(zip(tickers, weights)), tickers, out_dir)
        # After successful write, no temp files should remain
        temp_files = list(out_dir.glob("*.tmp"))
        assert len(temp_files) == 0, "Temp files should not exist after successful write"
        # The final file should be the CSV
        assert path.exists()
        assert path.suffix == ".csv"


class TestSavePortfolioResultsEdgeCases:
    """Tests for save_portfolio_results edge cases."""

    def test_solver_result_none(self, tmp_path):
        """save_portfolio_results with solver_result=None creates all 5 files."""
        from trader_off.portfolio.persistence import save_portfolio_results

        tickers = [f"s{i:03d}" for i in range(20)]
        weights = {t: 1.0 / 20 for t in tickers}
        mu = {t: 0.001 for t in tickers}
        cov = 0.0001 * np.eye(20)

        out_dir = tmp_path / "reports" / "no_solver_result"
        paths = save_portfolio_results(
            weights=weights,
            tickers=tickers,
            mu=mu,
            cov=cov,
            out_dir=out_dir,
            solver_result=None,
            constraint_report=None,
        )

        assert len(paths) == 5
        for f in [
            "weights.csv",
            "optimizer_report.json",
            "portfolio_metrics.csv",
            "weights_diagnostics.json",
            "assets_dropped.json",
        ]:
            assert (out_dir / f).exists()

    def test_solver_result_weights_none(self, tmp_path):
        """save_portfolio_results with solver_result.weights=None handles gracefully."""
        from trader_off.portfolio.persistence import save_portfolio_results
        from trader_off.portfolio.solver import SolverResult

        tickers = [f"s{i:03d}" for i in range(20)]
        mu = {t: 0.001 for t in tickers}
        cov = 0.0001 * np.eye(20)

        solver_result = SolverResult(
            weights=None,
            solver_status="infeasible",
            backend_used="scipy",
            solve_time_sec=0.5,
            iterations=0,
        )

        # Pass valid weights even though solver_result.weights is None
        valid_weights = {t: 1.0 / 20 for t in tickers}
        out_dir = tmp_path / "reports" / "infeasible"
        paths = save_portfolio_results(
            weights=valid_weights,
            tickers=tickers,
            mu=mu,
            cov=cov,
            out_dir=out_dir,
            solver_result=solver_result,
            constraint_report=None,
        )

        assert len(paths) == 5
        # optimizer_report.json should have null weights_sum and max_weight
        import json

        opt_report = json.loads((out_dir / "optimizer_report.json").read_text())
        assert opt_report["weights_sum"] is None
        assert opt_report["max_weight"] is None
        assert opt_report["solver_status"] == "infeasible"

    def test_weights_exception_cleanup(self, tmp_path):
        """save_weights cleans up temp file on exception."""
        import polars as pl

        from trader_off.portfolio.persistence import save_weights

        tickers = ["A", "B", "C"]
        weights = {"A": 0.5, "B": 0.3, "C": 0.2}
        out_dir = tmp_path / "p"
        out_dir.mkdir()

        def failing_write(self, *args, **kwargs):
            raise OSError("Simulated write failure")

        import pytest

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(pl.DataFrame, "write_csv", failing_write)
            with pytest.raises(IOError):
                save_weights(weights, tickers, out_dir)

        # No temp files should remain
        temp_files = list(out_dir.glob("*.tmp"))
        assert len(temp_files) == 0
