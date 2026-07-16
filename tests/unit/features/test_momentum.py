"""Tests for momentum feature computation (FR-0100)."""

from datetime import date, timedelta

import polars as pl
import pytest

from trader_off.features.momentum import compute_momentum_features


class TestComputeMomentumFeatures:
    """Unit tests for compute_momentum_features."""

    # AC-FR0100-1: Columns and dtype check
    def test_ac_fr0100_01_columns_and_dtype(self, five_assets_60_days):
        """AC-FR0100-1: Output must contain ret_5, ret_10, ret_20, ret_60 with Float64 dtype."""
        result = compute_momentum_features(five_assets_60_days)

        expected_cols = {"ret_5", "ret_10", "ret_20", "ret_60"}
        assert expected_cols.issubset(set(result.columns)), (
            f"Missing columns: {expected_cols - set(result.columns)}"
        )

        for col in expected_cols:
            assert result[col].dtype == pl.Float64, f"Column {col} dtype is {result[col].dtype}"

        # Original columns preserved
        for col in ["asset", "date", "close"]:
            assert col in result.columns

        # Row count preserved
        assert len(result) == len(five_assets_60_days)

    # AC-FR0100-2: ret_5 value correctness
    def test_ac_fr0100_02_ret5_value(self):
        """AC-FR0100-2: close=[10,11,9,12,14] with 6 rows -> ret_5[-1] == 14/10 - 1 == 0.4.

        Note: 6 rows (not 5) are needed because ret_5 = close[t]/close[t-5]-1
        requires at least 6 price points for the last ret_5 to be non-NaN.
        """
        # 6 close values so ret_5 at index 5 = close[5]/close[0]-1 = 14/10-1 = 0.4
        close_values = [10.0, 11.0, 9.0, 12.0, 14.0, 14.0]
        start_date = date(2024, 1, 1)
        data = []
        for i, close_val in enumerate(close_values):
            d = start_date + timedelta(days=i)
            data.append({
                "asset": "A",
                "date": d,
                "open": close_val * 0.99,
                "high": close_val * 1.02,
                "low": close_val * 0.98,
                "close": close_val,
                "volume": 1_000_000.0,
                "turnover": 0.02,
                "adj_factor": 1.0,
            })
        ohlcv = pl.DataFrame(data, schema={
            "asset": pl.Utf8,
            "date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "turnover": pl.Float64,
            "adj_factor": pl.Float64,
        })

        result = compute_momentum_features(ohlcv)

        ret5_values = result["ret_5"].to_list()
        expected = 14.0 / 10.0 - 1.0
        assert abs(ret5_values[-1] - expected) < 1e-9, (
            f"ret_5[-1]={ret5_values[-1]}, expected={expected}"
        )

    # AC-FR0100-3: Short history → NaN for long lookback
    def test_ac_fr0100_03_short_history_nan(self):
        """AC-FR0100-3: Asset B only 30 days → ret_60 all NaN, no exception."""
        assets = ["A", "B"]
        start_date = date(2024, 1, 1)
        data = []
        for asset in assets:
            for i in range(60 if asset == "A" else 30):
                d = start_date + timedelta(days=i)
                base_price = 10.0 + i * 0.1 + (ord(asset) - ord("A")) * 2.0
                data.append({
                    "asset": asset,
                    "date": d,
                    "open": base_price,
                    "high": base_price * 1.02,
                    "low": base_price * 0.98,
                    "close": base_price * (1.0 + 0.005 * (i % 5)),
                    "volume": 1_000_000.0,
                    "turnover": 0.02,
                    "adj_factor": 1.0,
                })
        ohlcv = pl.DataFrame(data, schema={
            "asset": pl.Utf8,
            "date": pl.Date,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "turnover": pl.Float64,
            "adj_factor": pl.Float64,
        })

        result = compute_momentum_features(ohlcv)

        asset_b = result.filter(pl.col("asset") == "B")
        assert asset_b["ret_60"].null_count() == 30, (
            f"Expected 30 NaN in ret_60 for asset B, got {asset_b['ret_60'].null_count()}"
        )
