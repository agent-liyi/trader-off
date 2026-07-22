"""Backtest runner (FR-0500).

Delegates backtest execution to quantide BacktestRunner.
No synthetic data — real OHLCV bars + actual strategy execution.
"""

import asyncio
import json
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import polars as pl
from loguru import logger

DEFAULT_STORE_PATH = ".quantide/bars/"
DEFAULT_CALENDAR_SOURCE = ".quantide/calendar/calendar.parquet"
FIXTURE_STORE_PATH = "tests/fixtures/v0.3.0/daily_bars_store"
FIXTURE_CALENDAR_SOURCE = "tests/fixtures/v0.2.0/ohlcv_50x252.parquet"


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
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _generate_inline_calendar(
    dates: list[date],
    output_path: Path,
) -> Path:
    """Generate an inline calendar parquet from a list of trading dates.

    Schema: {date, is_open=1, prev} where prev is the previous trading date
    index computed by the runner.

    FR-0100: Prepend one synthetic day before the earliest date so that
    calendar.day_shift(first_date, -1) returns a real previous day,
    avoiding ClockRewind in quantide's BacktestBroker.set_clock.

    Args:
        dates: Sorted list of unique trading dates.
        output_path: Path to write the calendar parquet to.

    Returns:
        Path to the generated calendar parquet.

    Raises:
        RuntimeError: If calendar generation fails.
    """
    try:
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build calendar DataFrame
        date_series = sorted(dates)

        # FR-0100: prepend synthetic previous day to avoid ClockRewind
        if date_series:
            from datetime import timedelta

            first = date_series[0]
            # Use a simple heuristic: go back one calendar day.
            # If first is a Monday, go back to Friday; otherwise back one day.
            if first.weekday() == 0:  # Monday
                prev_day = first - timedelta(days=3)  # Friday
            else:
                prev_day = first - timedelta(days=1)
            date_series = [prev_day] + date_series

        n = len(date_series)
        prev_indices = list(range(-1, n - 1))  # prev index: -1 for first day

        cal_df = pl.DataFrame(
            {
                "date": date_series,
                "is_open": [1] * n,
                "prev": prev_indices,
            },
            schema={"date": pl.Date, "is_open": pl.Int64, "prev": pl.Int64},
        )
        cal_df.write_parquet(output_path, compression="lz4")
        logger.info(f"Generated inline calendar ({n} dates) to {output_path}")
        return output_path
    except Exception as e:
        raise RuntimeError(f"calendar generation failed: {e}") from e


def _resolve_strategy_class(strategy_name: str) -> type:
    """Resolve strategy class from name.

    Args:
        strategy_name: Strategy name (e.g., 'lgbm_top20').

    Returns:
        Strategy class.
    """
    if strategy_name == "lgbm_top20":
        from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

        return LGBMTop20Strategy
    elif strategy_name == "optimized_topk":
        from trader_off.strategies.optimized_topk import OptimizedTopKStrategy

        return OptimizedTopKStrategy
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")


def run_backtest(
    model_version: str,
    strategy_name: str,
    start: date,
    end: date,
    capital: float,
    config: dict | None = None,
) -> BacktestResult:
    """Run a backtest using quantide BacktestRunner with real OHLCV data.

    Args:
        model_version: Model version string.
        strategy_name: Strategy name (e.g., 'lgbm_top20').
        start: Backtest start date.
        end: Backtest end date.
        capital: Initial capital.
        config: Optional strategy configuration dict. Supports keys:
            - store_path: Path to daily_bars store (default: v0.3.0 fixtures).
            - calendar_source: Path to OHLCV parquet for calendar generation.
            - universe: List of asset codes for the backtest universe.

    Returns:
        BacktestResult with summary, positions, trades, nav, and report_dir.
    """
    config = config or {}
    # Pass model_version through config for strategy use
    config.setdefault("model_version", model_version)

    # FR-0100: store_path resolution — prefer .quantide/ real data, fallback to fixture
    if "store_path" in config:
        store_path = config["store_path"]
        source_marker_store = "fixture store" if "fixtures/" in store_path else "real-data store"
    elif Path(DEFAULT_STORE_PATH).exists():
        store_path = DEFAULT_STORE_PATH
        source_marker_store = "real-data store"
    else:
        store_path = FIXTURE_STORE_PATH
        source_marker_store = "fixture store"

    # FR-0100: calendar_source resolution — same pattern
    if "calendar_source" in config:
        calendar_source = config["calendar_source"]
        source_marker_calendar = (
            "fixture calendar" if "fixtures/" in calendar_source else "real-data calendar"
        )
    elif Path(DEFAULT_CALENDAR_SOURCE).exists():
        calendar_source = DEFAULT_CALENDAR_SOURCE
        source_marker_calendar = "real-data calendar"
    else:
        calendar_source = FIXTURE_CALENDAR_SOURCE
        source_marker_calendar = "fixture calendar"

    # FR-0100: one-time INFO log for data source observability
    logger.info(f"store_path={store_path} ({source_marker_store})")
    logger.info(f"calendar_source={calendar_source} ({source_marker_calendar})")

    ts = _generate_timestamp()
    report_dir = Path(f"reports/backtest_{ts}")
    report_dir.mkdir(parents=True, exist_ok=True)

    # Step A: Generate inline calendar from fixture dates
    ohlcv = pl.read_parquet(calendar_source)
    date_col = "date" if "date" in ohlcv.columns else "trade_date"
    trade_dates: list[date] = sorted(ohlcv[date_col].unique().cast(pl.Date).to_list())

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_calendar_path = Path(tmp_dir) / f"calendar_{ts}.parquet"
        _generate_inline_calendar(trade_dates, tmp_calendar_path)

        # Step B & C: Connect daily_bars with store path and calendar
        # quantide imports at function scope per NFR-0200
        from quantide.data.models.daily_bars import daily_bars

        logger.info(f"Connecting daily_bars to {store_path}")
        daily_bars.connect(store_path, str(tmp_calendar_path))

        # Step D: Run backtest via quantide BacktestRunner
        from quantide.service.runner import BacktestRunner

        runner = BacktestRunner()
        strategy_cls = _resolve_strategy_class(strategy_name)

        logger.info(f"Running BacktestRunner with strategy={strategy_name}, capital={capital}")

        result = runner.run(
            strategy_cls=strategy_cls,
            config=config,
            start_date=start,
            end_date=end,
            initial_cash=capital,
            db_path=str(Path(tmp_dir) / "backtest.db"),
        )
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)

    portfolio_id = result.get("portfolio_id", "unknown")
    metrics_raw = result.get("metrics", {})

    # Map quantide metrics to v0.1.0 required keys
    summary = {
        "annualized_return": float(metrics_raw.get("annualized_return", 0.0)),
        "sharpe_ratio": float(metrics_raw.get("sharpe_ratio", 0.0)),
        "max_drawdown": float(metrics_raw.get("max_drawdown", 0.0)),
        "win_rate": float(metrics_raw.get("win_rate", 0.0)),
        "total_trades": int(metrics_raw.get("total_trades", 0)),
        "avg_turnover": float(metrics_raw.get("avg_turnover", 0.0)),
    }

    # Add optional extended keys from quantide
    for key in (
        "sortino",
        "drawdown_duration_days",
        "benchmark_return",
        "total_trades_real",
        "avg_turnover_real",
    ):
        if key in metrics_raw:
            summary[key] = metrics_raw[key]

    # Collect nav, positions, trades from database
    from quantide.data.sqlite import db

    assets_df = db.assets_all(portfolio_id=portfolio_id)
    if assets_df is not None and not assets_df.is_empty():
        nav_df = assets_df.select(
            [
                pl.col("dt").alias("date"),
                pl.col("total").alias("nav"),
            ]
        ).cast({"date": pl.Date, "nav": pl.Float64})
    else:
        nav_df = pl.DataFrame(schema={"date": pl.Date, "nav": pl.Float64})

    positions_df = db.positions_all(portfolio_id=portfolio_id)
    if positions_df is None or positions_df.is_empty():
        positions_df = pl.DataFrame(
            schema={"date": pl.Date, "asset": pl.Utf8, "weight": pl.Float64}
        )

    trades_df = db.trades_all(portfolio_id=portfolio_id)
    if trades_df is None or trades_df.is_empty():
        trades_df = pl.DataFrame(
            schema={"date": pl.Date, "asset": pl.Utf8, "action": pl.Utf8, "quantity": pl.Float64}
        )

    # Write output files
    nav_df.write_parquet(report_dir / f"nav_{ts}.parquet")
    positions_df.write_parquet(report_dir / f"positions_{ts}.parquet")
    trades_df.write_parquet(report_dir / f"trades_{ts}.parquet")
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    logger.info(f"Backtest finished. Reports saved to {report_dir}")
    return BacktestResult(
        summary=summary,
        positions=positions_df,
        trades=trades_df,
        nav=nav_df,
        report_dir=report_dir,
    )
