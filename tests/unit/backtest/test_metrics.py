"""Tests for performance metrics."""

from datetime import date, timedelta

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

    # returns dict with all 6 required keys
    def test_keys(self):
        """result dict has all 6 required keys with correct types."""
        # Generate 252 trading days of nav
        rng = __import__("numpy").random.RandomState(42)
        n = 252
        returns = rng.randn(n) * 0.02 + 0.001
        nav = 100.0 * __import__("numpy").cumprod(1.0 + returns)

        nav_df = _make_nav_df(nav.tolist())

        result = compute_performance_metrics(nav_df)

        required = {
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "total_trades",
            "avg_turnover",
        }
        assert set(result.keys()) == required

        assert isinstance(result["annualized_return"], float)
        assert isinstance(result["sharpe_ratio"], float)
        assert isinstance(result["max_drawdown"], float)
        assert isinstance(result["win_rate"], float)
        assert isinstance(result["total_trades"], int)
        assert isinstance(result["avg_turnover"], float)

    # max_drawdown for [100, 110, 105, 120, 115]
    def test_max_drawdown(self):
        """max_drawdown = (105-110)/110 ≈ -0.0455.

        Uses 35 values (30 + 5) to satisfy the 30-day minimum while
        preserving the peak=110 → trough=105 drawdown pattern.
        """
        # Pad with low values to not affect the running maximum
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
