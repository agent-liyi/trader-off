"""Performance metrics computation (FR-1200 / FR-0800).

Pure functions for computing annualized return, Sharpe ratio, max drawdown,
and win rate from a NAV time series.

FR-0800: total_trades and avg_turnover are no longer part of this function's
output — they are injected by the runner via quantide BacktestBroker.bills().
FR-0900: Public signature unchanged — compute_performance_metrics(nav_df).
"""

import numpy as np
import polars as pl

from trader_off.utils.exceptions import InsufficientDataError

MIN_DAYS = 30
TRADING_DAYS_PER_YEAR = 252


def _max_drawdown(nav: np.ndarray) -> float:
    """Compute max drawdown: min over t of (nav[t] - peak[t]) / peak[t]."""
    peak = np.maximum.accumulate(nav)
    drawdowns = (nav - peak) / peak
    return float(np.min(drawdowns))


def compute_performance_metrics(nav_df: pl.DataFrame) -> dict:
    """Compute performance metrics from a NAV time series.

    Args:
        nav_df: DataFrame with columns 'date' (Date) and 'nav' (Float64).

    Returns:
        Dict with keys: annualized_return, sharpe_ratio, max_drawdown,
        win_rate.
        total_trades and avg_turnover are provided by the runner (not this
        function) when trade data is available from BacktestBroker.bills().

    Raises:
        InsufficientDataError: If fewer than 30 NAV data points.
        ValueError: If NAV contains NaN/Inf values.
    """
    nav = nav_df["nav"].to_numpy()
    n = len(nav)

    if n < MIN_DAYS:
        raise InsufficientDataError(f"need at least {MIN_DAYS} days of NAV data, got {n}")

    if np.any(~np.isfinite(nav)):
        raise ValueError("NAV contains NaN or Inf values")

    # Daily returns
    daily_returns = np.diff(nav) / nav[:-1]

    # Annualized return
    total_return = nav[-1] / nav[0] - 1.0
    years = n / TRADING_DAYS_PER_YEAR
    annualized_return = float((1.0 + total_return) ** (1.0 / years) - 1.0)

    # Sharpe ratio (risk-free rate = 0)
    mean_ret = float(np.mean(daily_returns))
    std_ret = float(np.std(daily_returns, ddof=1))
    sharpe_ratio = (
        float((mean_ret / std_ret) * np.sqrt(TRADING_DAYS_PER_YEAR)) if std_ret > 0 else 0.0
    )

    # Max drawdown
    max_dd = _max_drawdown(nav)

    # Win rate: fraction of positive daily returns
    win_rate = float(np.mean(daily_returns > 0))

    return {
        "annualized_return": annualized_return,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
    }
