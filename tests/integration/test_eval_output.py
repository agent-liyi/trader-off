"""Integration tests for evaluation output (L2 contract simulation).

Covers the cross-module chain:
  evaluation.report → CSV output files
"""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from trader_off.evaluation.report import evaluate_predictions


def _make_aligned_data(
    n_dates: int = 10,
    n_assets: int = 50,
    seed: int = 42,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Generate aligned predictions and labels for evaluation testing."""
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

    preds = pl.DataFrame(
        rows_p,
        schema={"date": pl.Date, "asset": pl.Utf8, "score": pl.Float64},
    )
    labels = pl.DataFrame(
        rows_l,
        schema={"date": pl.Date, "asset": pl.Utf8, "label": pl.Float64},
    )
    return preds, labels


@pytest.mark.integration
class TestEvalOutput:
    """Integration: evaluation → CSV output files."""

    def test_ac_fr1300_04_csv_output(self, tmp_path):
        """AC-FR1300-04: prediction_quality.csv and layered_returns.csv files.

        Verifies that evaluate_predictions produces writable DataFrames
        for prediction quality and layered returns.
        """
        preds, labels = _make_aligned_data(n_dates=10, n_assets=50)

        report = evaluate_predictions(preds, labels)

        # Write prediction_quality.csv
        ic_csv = tmp_path / "prediction_quality.csv"
        report.ic_ts.write_csv(ic_csv)
        assert ic_csv.exists(), "Missing prediction_quality.csv"
        assert ic_csv.stat().st_size > 0, "prediction_quality.csv is empty"

        # Verify CSV content
        ic_df = pl.read_csv(ic_csv)
        assert "date" in ic_df.columns
        assert "ic" in ic_df.columns
        assert len(ic_df) == 10, (
            f"Expected 10 IC rows, got {len(ic_df)}"
        )

        # Write layered_returns.csv
        layered_csv = tmp_path / "layered_returns.csv"
        report.layered_returns.write_csv(layered_csv)
        assert layered_csv.exists(), "Missing layered_returns.csv"
        assert layered_csv.stat().st_size > 0, (
            "layered_returns.csv is empty"
        )

        # Verify layered returns structure
        lr_df = pl.read_csv(layered_csv)
        assert "layer" in lr_df.columns
        assert "mean_return" in lr_df.columns
        assert len(lr_df) == 5, (
            f"Expected 5 layers, got {len(lr_df)}"
        )

    def test_ac_fr1300_01_report_fields(self):
        """AC-FR1300-01: PredictionQualityReport has all required fields."""
        preds, labels = _make_aligned_data(n_dates=5, n_assets=50)

        report = evaluate_predictions(preds, labels)

        # Check all fields exist
        assert isinstance(report.ic_ts, pl.DataFrame)
        assert isinstance(report.rank_ic_ts, pl.DataFrame)
        assert isinstance(report.ic_mean, float)
        assert isinstance(report.ic_std, float)
        assert isinstance(report.rank_ic_mean, float)
        assert isinstance(report.rank_ic_std, float)
        assert isinstance(report.layered_returns, pl.DataFrame)

        # IC values should be in [-1, 1]
        if len(report.ic_ts) > 0:
            ic_vals = report.ic_ts["ic"].to_list()
            for v in ic_vals:
                assert -1.0 <= v <= 1.0, f"IC {v} outside [-1, 1]"
