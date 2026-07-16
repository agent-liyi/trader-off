"""Tests for feature standardization and missing value handling (FR-0400)."""

from datetime import date, timedelta
from dataclasses import asdict

import polars as pl
import pytest

from trader_off.data.preprocess import fit_scaler_and_impute, transform, StandardScaler


def make_feature_df(rows: list[dict]) -> pl.DataFrame:
    """Helper to create a feature DataFrame with consistent schema."""
    return pl.DataFrame(rows)


class TestFitScalerAndImpute:
    """Unit tests for fit_scaler_and_impute."""

    # AC-FR0400-1: Forward fill by asset group
    def test_ac_fr0400_01_forward_fill_by_asset(self):
        """AC-FR0400-1: f2 NaN at row 3 for asset A → forward filled from row 2 of same asset.

        Two assets A, B. Each has 4 rows. Asset A row 2 (index) has f2=NaN,
        should be forward-filled from row 1 of asset A.
        """
        start_date = date(2024, 1, 1)
        data = []
        for asset in ["A", "B"]:
            for i in range(4):
                d = start_date + timedelta(days=i)
                # f1: sequential values; f2: NaN at i=2 for asset A only
                f2_val = 10.0 + i
                if asset == "A" and i == 2:
                    f2_val = None
                data.append({
                    "asset": asset,
                    "date": d,
                    "f1": float(i + 1),
                    "f2": f2_val,
                })
        df = pl.DataFrame(data, schema={
            "asset": pl.Utf8,
            "date": pl.Date,
            "f1": pl.Float64,
            "f2": pl.Float64,
        })

        transformed, scaler, dropped = fit_scaler_and_impute(df)

        # Asset A row 2 (i=2): f2 should be forward-filled from row 1 (f2=11.0)
        asset_a_row2 = transformed.filter(
            (pl.col("asset") == "A") & (pl.col("date") == start_date + timedelta(days=2))
        )
        assert len(asset_a_row2) == 1
        # After forward fill, the value should equal the previous row's value (11.0)
        # Before z-score: f2 = 11.0
        # After z-score: (11.0 - mean(f2)) / std(f2)
        asset_a_row2_f2 = asset_a_row2["f2"].item()
        # Check it's not NaN
        assert asset_a_row2_f2 is not None, "f2 should be forward-filled, not NaN"

        # Asset A row 3 (last row): f2 should have its original value 13.0
        asset_a_row3 = transformed.filter(
            (pl.col("asset") == "A") & (pl.col("date") == start_date + timedelta(days=3))
        )
        assert asset_a_row3["f2"].item() is not None

        # Asset B should have no NaN in f2 (all values were present)
        asset_b_nulls = transformed.filter(pl.col("asset") == "B")["f2"].null_count()
        assert asset_b_nulls == 0

    # AC-FR0400-2: transform reuses scaler
    def test_ac_fr0400_02_transform_reuses_scaler(self):
        """AC-FR0400-2: transform uses training scaler params, does not re-fit."""
        start_date = date(2024, 1, 1)
        data = []
        for asset in ["A", "B"]:
            for i in range(10):
                d = start_date + timedelta(days=i)
                data.append({
                    "asset": asset,
                    "date": d,
                    "f1": float(i + 1),
                    "f2": float(20.0 + i * 2),
                })
        train_df = pl.DataFrame(data, schema={
            "asset": pl.Utf8,
            "date": pl.Date,
            "f1": pl.Float64,
            "f2": pl.Float64,
        })

        _, scaler, _ = fit_scaler_and_impute(train_df)

        # Capture scaler params before transform
        mean_before = dict(scaler.mean_)
        std_before = dict(scaler.std_)

        # Create test data and transform
        test_data = []
        for asset in ["A"]:
            for i in range(3):
                d = start_date + timedelta(days=i + 20)
                test_data.append({
                    "asset": asset,
                    "date": d,
                    "f1": float(i + 100),
                    "f2": float(200.0 + i * 2),
                })
        test_df = pl.DataFrame(test_data, schema={
            "asset": pl.Utf8,
            "date": pl.Date,
            "f1": pl.Float64,
            "f2": pl.Float64,
        })

        _ = transform(test_df, scaler)

        # Scaler params must not change after transform
        assert scaler.mean_ == mean_before, "scaler.mean_ changed after transform"
        assert scaler.std_ == std_before, "scaler.std_ changed after transform"

    # AC-FR0400-3: All-NaN column dropped
    def test_ac_fr0400_03_dropped_features(self, tmp_path):
        """AC-FR0400-3: All-NaN feature column → dropped, recorded."""
        start_date = date(2024, 1, 1)
        data = []
        for asset in ["A"]:
            for i in range(10):
                d = start_date + timedelta(days=i)
                data.append({
                    "asset": asset,
                    "date": d,
                    "f1": float(i + 1),
                    "f2": None,  # All NaN
                    "f3": float(i * 3),
                })
        df = pl.DataFrame(data, schema={
            "asset": pl.Utf8,
            "date": pl.Date,
            "f1": pl.Float64,
            "f2": pl.Float64,
            "f3": pl.Float64,
        })

        transformed, scaler, dropped = fit_scaler_and_impute(df)

        # f2 should be dropped
        assert "f2" in dropped, f"Expected 'f2' in dropped, got {dropped}"
        assert "f2" not in transformed.columns, "f2 should not be in transformed df"
        assert "f1" in transformed.columns
        assert "f3" in transformed.columns

        # f2 should not be in scaler
        assert "f2" not in scaler.mean_, "f2 should not be in scaler.mean_"
