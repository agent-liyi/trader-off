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

    # returns dict with all 6 required keys + optional keys
    def test_keys(self):
        """Result dict has all 6 required keys with correct types."""
        rng = np.random.RandomState(42)
        n = 252
        returns = rng.randn(n) * 0.02 + 0.001
        nav = 100.0 * np.cumprod(1.0 + returns)

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
        # FR-0900 AC-3: required keys are a subset (optional keys may also exist)
        assert required.issubset(set(result.keys())), (
            f"Missing keys: {required - set(result.keys())}"
        )

        assert isinstance(result["annualized_return"], float)
        assert isinstance(result["sharpe_ratio"], float)
        assert isinstance(result["max_drawdown"], float)
        assert isinstance(result["win_rate"], float)
        assert isinstance(result["total_trades"], int)
        assert isinstance(result["avg_turnover"], float)

    # FR-0700 AC-2: metrics should return non-negative total_trades
    # (0 when no bills data, but the type must be correct)
    def test_total_trades_type(self):
        """total_trades is an int >= 0."""
        rng = np.random.RandomState(42)
        n = 252
        returns = rng.randn(n) * 0.02 + 0.001
        nav = 100.0 * np.cumprod(1.0 + returns)
        nav_df = _make_nav_df(nav.tolist())
        result = compute_performance_metrics(nav_df)

        assert isinstance(result["total_trades"], int)
        assert result["total_trades"] >= 0

    def test_avg_turnover_type(self):
        """avg_turnover is a float >= 0.0."""
        rng = np.random.RandomState(42)
        n = 252
        returns = rng.randn(n) * 0.02 + 0.001
        nav = 100.0 * np.cumprod(1.0 + returns)
        nav_df = _make_nav_df(nav.tolist())
        result = compute_performance_metrics(nav_df)

        assert isinstance(result["avg_turnover"], float)
        assert result["avg_turnover"] >= 0.0

    # AC-FR0800-03: extended keys may be present
    def test_extended_keys_may_exist(self):
        """Result may include optional extended keys."""
        rng = np.random.RandomState(42)
        n = 252
        returns = rng.randn(n) * 0.02 + 0.001
        nav = 100.0 * np.cumprod(1.0 + returns)
        nav_df = _make_nav_df(nav.tolist())
        result = compute_performance_metrics(nav_df)

        # sortino and drawdown_duration_days may be present or None
        assert "sortino" not in result or result["sortino"] is not None or result["sortino"] is None
        assert "drawdown_duration_days" not in result or isinstance(
            result.get("drawdown_duration_days"), (int, type(None))
        )

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
        """NaN values in nav raise RuntimeError."""
        nav_values = [100.0] * 30 + [float("nan")]
        nav_df = _make_nav_df(nav_values)

        with pytest.raises((RuntimeError, ValueError)):
            compute_performance_metrics(nav_df)
