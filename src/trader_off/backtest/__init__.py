"""Backtesting: runner and performance metrics."""

from trader_off.backtest.runner import BacktestResult, run_backtest
from trader_off.backtest.metrics import compute_performance_metrics

__all__ = [
    "run_backtest",
    "BacktestResult",
    "compute_performance_metrics",
]
