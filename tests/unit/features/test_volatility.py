"""Tests for volatility feature computation (FR-0200)."""

from datetime import date, timedelta

import polars as pl

from trader_off.features.volatility import compute_volatility_features


class TestComputeVolatilityFeatures:
    """Unit tests for compute_volatility_features."""

    # AC-FR0200-01: Columns and dtype check
    def test_ac_fr0200_01_columns_dtype(self, five_assets_60_days):
        """AC-FR0200-01: Output must contain vol_10, vol_20, vol_60 with Float64 dtype."""
        result = compute_volatility_features(five_assets_60_days)

        expected_cols = {"vol_10", "vol_20", "vol_60"}
        assert expected_cols.issubset(set(result.columns)), (
            f"Missing columns: {expected_cols - set(result.columns)}"
        )

        for col in expected_cols:
            assert result[col].dtype == pl.Float64, f"Column {col} dtype is {result[col].dtype}"

        assert len(result) == len(five_assets_60_days)

    # AC-FR0200-02: Zero std for constant returns
    def test_ac_fr0200_02_zero_std(self):
        """AC-FR0200-02: Geometric close series → constant 1% returns → vol_10[-1] == 0.0.

        Note: Uses geometric progression (not arithmetic) to produce truly
        constant daily returns of exactly 0.01 each.
        """
        # Geometric progression: close[i] = 100 * 1.01^i → constant 1% returns
        close_values = [100.0 * (1.01**i) for i in range(11)]
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

        result = compute_volatility_features(ohlcv)

        vol10_values = result["vol_10"].to_list()
        # With constant returns, std should be ~0
        assert abs(vol10_values[-1]) < 1e-9, (
            f"vol_10[-1]={vol10_values[-1]}, expected ~0.0"
        )

    # AC-FR0200-03: min_samples behavior
    def test_ac_fr0200_03_min_periods(self):
        """AC-FR0200-03: 11 close values → 10 daily returns.

        vol_10 with min_samples=10: first 10 values (indices 0-9) should be NaN,
        index 10 should have a value.
        """
        # Geometric progression for consistent returns
        close_values = [100.0 * (1.01**i) for i in range(11)]
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

        result = compute_volatility_features(ohlcv)

        vol10 = result["vol_10"].to_list()
        # First 10 values (indices 0-9) should be NaN
        for i in range(10):
            assert vol10[i] is None, f"vol_10[{i}]={vol10[i]}, expected None"
        # Index 10 should have a float value (std of constant returns ≈ 0)
        assert isinstance(vol10[10], float), (
            f"vol_10[10]={vol10[10]}, expected float"
        )
