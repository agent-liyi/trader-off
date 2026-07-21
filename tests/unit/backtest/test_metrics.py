"""Tests for performance metrics — FR-0700/FR-0800/FR-0900."""

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from trader_off.backtest.metrics import compute_performance_metrics
from trader_off.utils.exceptions import InsufficientDataError


def _make_nav_df(values: list[float]) -> pl.DataFrame:
    """Create a nav DataFrame from a list of float values."""
    start = date(2024, 1, 1)
    return pl.DataFrame(
        {
            "date": [start + timedelta(days=i) for i in range(len(values))],
            "nav": values,
        },
        schema={"date": pl.Date, "nav": pl.Float64},
    )


class TestComputePerformanceMetrics:
    """Unit tests for compute_performance_metrics."""

    # FR-0800: returns core 4 keys only (total_trades/avg_turnover come from runner)
    def test_keys(self):
        """Result dict has core keys with correct types."""
        rng = np.random.RandomState(42)
        n = 252
        returns = rng.randn(n) * 0.02 + 0.001
        nav = 100.0 * np.cumprod(1.0 + returns)

        nav_df = _make_nav_df(nav.tolist())
        result = compute_performance_metrics(nav_df)

        core_keys = {
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
        }
        assert core_keys.issubset(set(result.keys())), (
            f"Missing core keys: {core_keys - set(result.keys())}"
        )

        assert isinstance(result["annualized_return"], float)
        assert isinstance(result["sharpe_ratio"], float)
        assert isinstance(result["max_drawdown"], float)
        assert isinstance(result["win_rate"], float)

    # FR-0800: total_trades and avg_turnover no longer hardcoded
    def test_no_trade_keys_when_standalone(self):
        """total_trades/avg_turnover absent when compute_performance_metrics
        is called standalone (no trade data from broker)."""
        rng = np.random.RandomState(42)
        n = 252
        returns = rng.randn(n) * 0.02 + 0.001
        nav = 100.0 * np.cumprod(1.0 + returns)
        nav_df = _make_nav_df(nav.tolist())
        result = compute_performance_metrics(nav_df)

        # These keys are provided by the runner, not by this function
        assert "total_trades" not in result
        assert "avg_turnover" not in result

    # max_drawdown for [100, 110, 105, 120, 115]
    def test_max_drawdown(self):
        """max_drawdown = (105-110)/110 ≈ -0.0455."""
        nav_values = [50.0] * 30 + [100.0, 110.0, 105.0, 120.0, 115.0]
        nav_df = _make_nav_df(nav_values)
        result = compute_performance_metrics(nav_df)

        expected_dd = (105.0 - 110.0) / 110.0
        assert abs(result["max_drawdown"] - expected_dd) < 1e-6, (
            f"max_drawdown={result['max_drawdown']}, expected≈{expected_dd}"
        )

    # <30 days → InsufficientDataError
    def test_insufficient_data(self):
        """10 rows of nav → InsufficientDataError."""
        nav_values = [100.0 + i for i in range(10)]
        nav_df = _make_nav_df(nav_values)

        with pytest.raises(InsufficientDataError, match="need at least 30 days"):
            compute_performance_metrics(nav_df)

    # AC-FR0800-05: NaN/Inf in nav → error
    def test_nan_in_nav_raises(self):
        """NaN values in nav raise ValueError."""
        nav_values = [100.0] * 30 + [float("nan")]
        nav_df = _make_nav_df(nav_values)

        with pytest.raises(ValueError):
            compute_performance_metrics(nav_df)
