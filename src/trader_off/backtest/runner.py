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

DEFAULT_STORE_PATH = "tests/fixtures/v0.3.0/daily_bars_store"
DEFAULT_CALENDAR_SOURCE = "tests/fixtures/v0.2.0/ohlcv_50x252.parquet"


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


@dataclass
class PaperTradeResult:
    """Container for paper trading results.

    Same field structure as BacktestResult for serialization compatibility.

    Attributes:
        summary: Performance metrics dict (6 required keys + optional extensions).
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


class PaperBrokerAdapter:
    """Adapter wrapping PaperBroker to expose BacktestBroker-compatible interface.

    Strategies (LGBMTop20Strategy, OptimizedTopKStrategy) expect:
        - total_asset() as a callable method
        - market_value() as a callable method
        - positions as a dict[str, Position]
        - trade_target_pct() as an async method

    PaperBroker provides:
        - total_assets as a property
        - positions as a List[Position]
        - trade_target_pct() as an async method (same signature)
        - No market_value() method

    This adapter bridges the gap so strategies require zero code changes (AC-06).
    """

    def __init__(self, paper_broker):
        """Wrap a PaperBroker instance.

        Args:
            paper_broker: quantide.service.sim_broker.PaperBroker instance.
        """
        self._paper = paper_broker

    def total_asset(self) -> float:
        """Return total assets (cash + market value).

        Delegates to PaperBroker.total_assets property, adapted as a method
        to match the BacktestBroker interface that strategies expect.
        """
        return self._paper.total_assets

    def market_value(self) -> float:
        """Return total market value of all positions.

        Computed as sum of position.mv since PaperBroker has no direct
        market_value() method.
        """
        return sum(pos.mv for pos in self._paper.positions)

    @property
    def positions(self) -> dict:
        """Return current positions as a dict keyed by asset code.

        PaperBroker.positions returns a List[Position]; strategies expect
        a dict[str, Position] for .keys() / [asset] access patterns.
        """
        return {pos.asset: pos for pos in self._paper.positions}

    async def trade_target_pct(
        self,
        asset: str,
        target_pct: float,
        price: float = 0,
        order_time=None,
        timeout: float = 0.5,
    ):
        """Delegate trade_target_pct to the underlying PaperBroker.

        Args:
            asset: Asset code to trade.
            target_pct: Target portfolio percentage (0.0 - 1.0).
            price: Limit price (0 for market price).
            order_time: Order timestamp.
            timeout: Timeout in seconds.

        Returns:
            TradeResult from PaperBroker.
        """
        return await self._paper.trade_target_pct(
            asset, target_pct, price=price, order_time=order_time, timeout=timeout
        )

    def __getattr__(self, name):
        """Fallback: delegate any unknown attribute to the PaperBroker instance.

        This covers methods like on_day_open, on_day_close, cancel_order, etc.
        that strategies may call indirectly, as well as properties like cash,
        principal, etc.
        """
        return getattr(self._paper, name)


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
    store_path = config.get("store_path", DEFAULT_STORE_PATH)
    calendar_source = config.get("calendar_source", DEFAULT_CALENDAR_SOURCE)

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


def run_paper_trade(
    strategy_name: str,
    end_date: date,
    initial_cash: float,
    config: dict | None = None,
) -> PaperTradeResult:
    """Run a paper trading session using quantide PaperBroker.

    Unlike run_backtest, this uses PaperBroker (local matching + sqlite persistence)
    instead of BacktestBroker (historical replay). The same strategy code runs
    unchanged via PaperBrokerAdapter.

    All quantide imports are function-scope per NFR-0100.

    Args:
        strategy_name: Strategy name (e.g., 'lgbm_top20', 'optimized_topk').
        end_date: Trading end date (session loop runs days <= end_date).
        initial_cash: Initial capital for the paper account.
        config: Optional strategy configuration dict. Supports keys:
            - store_path: Path to daily_bars store.
            - calendar_source: Path to OHLCV parquet for calendar generation.
            - universe: List of asset codes.

    Returns:
        PaperTradeResult with summary, positions, trades, nav, and report_dir.
    """
    config = config or {}
    store_path = config.get("store_path", DEFAULT_STORE_PATH)
    calendar_source = config.get("calendar_source", DEFAULT_CALENDAR_SOURCE)
    universe = config.get("universe", [])

    ts = _generate_timestamp()
    report_dir = Path(f"reports/paper_trade_{ts}")
    report_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Init db BEFORE PaperBroker (AC-FR0100-02)
    from quantide.data.sqlite import db

    db.init(str(report_dir / "paper_state.sqlite"))

    # Step 2: Generate inline calendar from fixture dates
    ohlcv = pl.read_parquet(calendar_source)
    date_col = "date" if "date" in ohlcv.columns else "trade_date"
    trade_dates: list[date] = sorted(ohlcv[date_col].unique().cast(pl.Date).to_list())

    # Auto-derive universe from OHLCV if not provided (FR-0200 blocker fix)
    if not universe and "asset" in ohlcv.columns:
        universe = ohlcv["asset"].unique().to_list()
        logger.info(f"Auto-derived {len(universe)} assets from calendar source {calendar_source}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_calendar_path = Path(tmp_dir) / f"calendar_{ts}.parquet"
        _generate_inline_calendar(trade_dates, tmp_calendar_path)

        # Step 3: Connect daily_bars (AC-FR0100-03)
        from quantide.data.models.daily_bars import daily_bars

        daily_bars.connect(store_path, str(tmp_calendar_path))

        # Step 4: Instantiate PaperBroker (AC-FR0100-01)
        import uuid

        from quantide.service.sim_broker import PaperBroker

        portfolio_id = str(uuid.uuid4())
        paper = PaperBroker(
            portfolio_id=portfolio_id,
            principal=initial_cash,
            commission=1e-4,
        )

        # Step 5: Wrap in PaperBrokerAdapter (AC-FR0100-05)
        adapter = PaperBrokerAdapter(paper)

        # Step 6: Resolve and instantiate strategy
        strategy_cls = _resolve_strategy_class(strategy_name)
        strategy = strategy_cls(adapter, config)

        # Step 7: Session loop drive strategy on PaperBroker
        from quantide.core.enums import Topics
        from quantide.core.message import msg_hub

        # Filter trading dates <= end_date
        loop_dates = [d for d in trade_dates if d <= end_date]

        if not loop_dates:
            logger.warning(f"No trading dates found <= {end_date}")

        # Build universe set for asset collection
        universe_set = set(universe) if isinstance(universe, list) else set()

        for d in loop_dates:
            # Collect assets: universe + current positions
            current_assets = set(universe_set)
            for pos in paper.positions:
                current_assets.add(pos.asset)
            assets = list(current_assets) if current_assets else None

            if not assets:
                logger.warning(f"No assets for {d}, skipping")
                continue

            # Get bars for this day from daily_bars store
            bars_df = daily_bars.get_bars_in_range(d, d, assets)
            if bars_df.is_empty():
                logger.warning(f"No bar data for {d}, skipping")
                continue

            # Build quote dict and close_prices dict (AC-FR0100-06)
            quote: dict = {}
            close_prices: dict[str, float] = {}
            for row in bars_df.to_dicts():
                asset = row["asset"]
                quote[asset] = {
                    "lastPrice": row.get("close", 0),
                    "open": row.get("open", 0),
                    "high": row.get("high", 0),
                    "low": row.get("low", 0),
                    "volume": row.get("volume", 0),
                    "amount": row.get("amount", 0),
                }
                close_prices[asset] = row.get("close", 0)

            # Patch _get_quote so trade_target_pct can determine prices
            # (PaperBroker._get_quote normally queries live_quote / market_data;
            #  in session loop we inject bar data per day)
            original_get_quote = paper._get_quote

            def _make_get_quote(day_quote):
                def _get_quote(asset):
                    return day_quote.get(asset)

                return _get_quote

            paper._get_quote = _make_get_quote(quote)

            try:
                # Publish quotes -> triggers _on_quote_update market value update
                msg_hub.publish(Topics.QUOTES_ALL.value, quote)

                # Day open / close cycle (AC-FR0100-04 session loop)
                import asyncio

                tm = datetime(d.year, d.month, d.day, 9, 30)
                tm_close = datetime(d.year, d.month, d.day, 15, 0)

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(paper.on_day_open())
                    loop.run_until_complete(strategy.on_day_open(tm))
                    loop.run_until_complete(paper.on_day_close(close_prices))
                    loop.run_until_complete(strategy.on_day_close(tm_close))
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            finally:
                paper._get_quote = original_get_quote

    # Step 8: Collect results from db (AC-FR0100-07)
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

    total_trades = trades_df.height
    summary = {
        "annualized_return": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "total_trades": total_trades,
        "avg_turnover": 0.0,
    }

    logger.info(f"Paper trade finished. Reports saved to {report_dir}")
    return PaperTradeResult(
        summary=summary,
        positions=positions_df,
        trades=trades_df,
        nav=nav_df,
        report_dir=report_dir,
    )
