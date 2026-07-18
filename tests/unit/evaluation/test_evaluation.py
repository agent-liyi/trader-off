"""Tests for prediction evaluation."""

from datetime import date, timedelta

import numpy as np
import polars as pl

from trader_off.evaluation.ic import compute_layered_returns, ic_pearson, ic_spearman
from trader_off.evaluation.report import (
    PredictionQualityReport,
    evaluate_predictions,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_aligned_data(
    n_dates: int = 10,
    n_assets: int = 100,
    seed: int = 42,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Generate aligned predictions and labels."""
    rng = np.random.RandomState(seed)
    start = date(2024, 1, 1)
    rows_p, rows_l = [], []

    for d_idx in range(n_dates):
        d = start + timedelta(days=d_idx)
        for a in range(n_assets):
            asset = f"{a:04d}.SZ"
            score = rng.randn()
            label = score * 0.3 + rng.randn() * 0.1
            rows_p.append({"date": d, "asset": asset, "score": score})
            rows_l.append({"date": d, "asset": asset, "label": label})

    preds = pl.DataFrame(rows_p, schema={"date": pl.Date, "asset": pl.Utf8, "score": pl.Float64})
    labels = pl.DataFrame(rows_l, schema={"date": pl.Date, "asset": pl.Utf8, "label": pl.Float64})
    return preds, labels


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestICFunctions:
    """Unit tests for ic_pearson and ic_spearman."""

    def test_ic_pearson_range(self):
        """IC Pearson values must be in [-1, 1] range."""
        pred = pl.Series("pred", [1.0, 2.0, 3.0, 4.0, 5.0])
        label = pl.Series("label", [2.0, 4.0, 6.0, 8.0, 10.0])
        result = ic_pearson(pred, label)
        assert -1.0 <= result <= 1.0
        # Perfect positive correlation
        assert result > 0.99

    def test_ic_spearman_range(self):
        """IC Spearman values must be in [-1, 1] range."""
        pred = pl.Series("pred", [1.0, 2.0, 3.0, 4.0, 5.0])
        label = pl.Series("label", [1.0, 2.0, 3.0, 4.0, 5.0])
        result = ic_spearman(pred, label)
        assert -1.0 <= result <= 1.0
        assert result > 0.99


class TestLayeredReturns:
    """Unit tests for compute_layered_returns."""

    def test_compute_layered_returns_shape(self):
        """Layered returns must have 5 layers with mean_return column."""
        rng = np.random.RandomState(42)
        n = 100
        preds = pl.DataFrame(
            {
                "date": [date(2024, 1, 1)] * n,
                "asset": [f"{i:04d}.SZ" for i in range(n)],
                "score": rng.randn(n),
            },
            schema={"date": pl.Date, "asset": pl.Utf8, "score": pl.Float64},
        )
        labels = pl.DataFrame(
            {
                "date": [date(2024, 1, 1)] * n,
                "asset": [f"{i:04d}.SZ" for i in range(n)],
                "label": rng.randn(n) * 0.1,
            },
            schema={"date": pl.Date, "asset": pl.Utf8, "label": pl.Float64},
        )

        result = compute_layered_returns(preds, labels, n_layers=5)
        assert len(result) == 5
        assert set(result.columns) == {"layer", "mean_return"}


class TestEvaluatePredictions:
    """Unit tests for evaluate_predictions."""

    # returns PredictionQualityReport
    def test_report_fields(self):
        """evaluate_predictions returns PredictionQualityReport."""
        preds, labels = _make_aligned_data(n_dates=20, n_assets=50)
        report = evaluate_predictions(preds, labels)

        assert isinstance(report, PredictionQualityReport)
        assert isinstance(report.ic_ts, pl.DataFrame)
        assert isinstance(report.rank_ic_ts, pl.DataFrame)
        assert isinstance(report.layered_returns, pl.DataFrame)
        assert isinstance(report.ic_mean, float)
        assert isinstance(report.ic_std, float)
        assert isinstance(report.rank_ic_mean, float)
        assert isinstance(report.rank_ic_std, float)

        # ic_ts should have columns date, ic
        assert "date" in report.ic_ts.columns
        assert "ic" in report.ic_ts.columns
        assert "date" in report.rank_ic_ts.columns
        assert "rank_ic" in report.rank_ic_ts.columns

    # ic_ts row count = unique dates, ic in [-1,1]
    def test_ic_range(self):
        """ic_ts rows = n_unique_dates, ic values in [-1,1]."""
        preds, labels = _make_aligned_data(n_dates=10, n_assets=100)
        report = evaluate_predictions(preds, labels)

        n_dates = preds["date"].n_unique()
        assert len(report.ic_ts) == n_dates

        ic_vals = report.ic_ts["ic"].to_list()
        for v in ic_vals:
            assert -1.0 <= v <= 1.0, f"ic={v} out of range"

    # __all__ exports
    def test_imports(self):
        """__all__ contains ic_pearson, ic_spearman, compute_layered_returns."""
        from trader_off import evaluation as ev

        assert "ic_pearson" in ev.__all__
        assert "ic_spearman" in ev.__all__
        assert "compute_layered_returns" in ev.__all__

    # output files written
    def test_csv_output(self, tmp_path):
        """prediction_quality.csv and layered_returns.csv written."""
        preds, labels = _make_aligned_data(n_dates=10, n_assets=100)
        report = evaluate_predictions(preds, labels)

        out_dir = tmp_path / "reports" / "backtest_test"
        out_dir.mkdir(parents=True)

        report.ic_ts.write_csv(out_dir / "prediction_quality.csv")
        report.layered_returns.write_csv(out_dir / "layered_returns.csv")

        assert (out_dir / "prediction_quality.csv").exists()
        assert (out_dir / "layered_returns.csv").exists()

        # Verify CSV content
        ic_csv = pl.read_csv(out_dir / "prediction_quality.csv")
        assert len(ic_csv) > 0
        layered_csv = pl.read_csv(out_dir / "layered_returns.csv")
        assert len(layered_csv) == 5
