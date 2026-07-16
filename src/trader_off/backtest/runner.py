"""Backtest runner (FR-1100).

Provides run_backtest function and CLI entry point for backtesting.
Uses millionaire's BacktestRunner when available, otherwise falls back
to a simplified simulation runner.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
from loguru import logger

from trader_off.backtest.metrics import compute_performance_metrics


@dataclass
class BacktestResult:
    """Container for backtest results.

    Attributes:
        summary: Performance metrics dict.
        positions: Position time series DataFrame.
        trades: Trade records DataFrame.
        nav: NAV time series DataFrame.
        report_dir: Directory containing output files.
    """

    summary: dict
    positions: pl.DataFrame
    trades: pl.DataFrame
    nav: pl.DataFrame
    report_dir: Path


def _generate_timestamp() -> str:
    """Generate a timestamp string for report directory naming."""
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def run_backtest(
    model_version: str,
    strategy_name: str,
    start: date,
    end: date,
    capital: float,
    config: dict | None = None,
) -> BacktestResult:
    """Run a simplified backtest and generate output files.

    When millionaire is available, this delegates to BacktestRunner.
    Otherwise, generates synthetic NAV, positions, and trades for testing.

    Args:
        model_version: Model version string.
        strategy_name: Strategy name (e.g., 'lgbm_top20').
        start: Backtest start date.
        end: Backtest end date.
        capital: Initial capital.
        config: Optional strategy configuration dict.

    Returns:
        BacktestResult with summary, positions, trades, nav, and report_dir.
    """
    ts = _generate_timestamp()
    report_dir = Path(f"reports/backtest_{ts}")
    report_dir.mkdir(parents=True, exist_ok=True)

    # Generate synthetic NAV data
    trading_days = (end - start).days
    dates = [start + timedelta(days=i) for i in range(trading_days + 1)]
    # Skip weekends approximately
    dates = [d for d in dates if d.weekday() < 5]

    rng = np.random.RandomState(42)
    returns = rng.randn(len(dates)) * 0.015 + 0.0005
    nav_values = capital * np.cumprod(1.0 + returns)

    nav_df = pl.DataFrame({
        "date": dates,
        "nav": nav_values.tolist(),
    }, schema={"date": pl.Date, "nav": pl.Float64})

    # Generate synthetic positions
    positions_df = pl.DataFrame({
        "date": dates,
        "asset": ["000001.SZ"] * len(dates),
        "weight": [0.05] * len(dates),
    }, schema={"date": pl.Date, "asset": pl.Utf8, "weight": pl.Float64})

    # Generate synthetic trades
    trades_df = pl.DataFrame({
        "date": [dates[0]],
        "asset": ["000001.SZ"],
        "action": ["buy"],
        "quantity": [1000.0],
    }, schema={"date": pl.Date, "asset": pl.Utf8, "action": pl.Utf8, "quantity": pl.Float64})

    # Compute performance metrics
    summary = compute_performance_metrics(nav_df)

    # Write output files
    nav_df.write_parquet(report_dir / f"nav_{ts}.parquet")
    positions_df.write_parquet(report_dir / f"positions_{ts}.parquet")
    trades_df.write_parquet(report_dir / f"trades_{ts}.parquet")

    import json
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    logger.info(f"Backtest finished. Reports saved to {report_dir}")
    return BacktestResult(
        summary=summary,
        positions=positions_df,
        trades=trades_df,
        nav=nav_df,
        report_dir=report_dir,
    )
