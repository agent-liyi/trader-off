"""OptimizedTopKStrategy — FR-4200.

A portfolio strategy that uses weights produced by the portfolio optimizer
(Max Sharpe). Falls back to LGBMTop20Strategy when:
  - weights.csv is missing
  - weights.csv is stale (mtime > 5 trading days old)

The strategy inherits from BaseStrategy (v0.1.0 interface).
On each trading day (on_day_open), it issues broker.trade_target_pct calls
for each asset in the optimized portfolio.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from trader_off.strategies.compat import BaseStrategy
from trader_off.strategies.lgbm_top20 import LGBMTop20Strategy

if TYPE_CHECKING:
    pass


#: Number of trading days after which weights.csv is considered stale.
STALE_DAYS = 5


class OptimizedTopKStrategy(BaseStrategy):
    """Portfolio strategy using optimizer-produced weights.

    On init, loads ``weights.csv`` from ``weights_dir`` (configurable per T-4).
    If the file is missing or stale (>5 days old), falls back to the
    LGBMTop20Strategy behavior with a WARNING log.

    Attributes:
        weights: Dict mapping asset ticker to weight, or None if not loaded.
        top_k: Number of top assets to hold (from config).
        weights_dir: Directory containing weights.csv (from config).
        version: Version string for extra dict.
    """

    def __init__(self, broker, config: dict | None = None):
        """Initialize the strategy.

        Args:
            broker: Broker instance for order execution.
            config: Configuration dict with keys:
                - weights_dir (str): Directory containing weights.csv.
                  Default: "reports/portfolio_latest".
                - top_k (int): Number of top assets to hold.
                  Default: 20.
                - model_version (str): Model version string for extra dict.
                  Default: "".
        """
        super().__init__(broker, config)
        config = config or {}
        self.weights_dir: Path = Path(config.get("weights_dir", "reports/portfolio_latest"))
        self.top_k: int = int(config.get("top_k", 20))
        self.model_version: str = config.get("model_version", "")

        self.weights: dict[str, float] | None = None
        self._position_cache: dict[str, float] = {}
        self._fallback = False

    def _load_weights(self) -> bool:
        """Load weights from weights.csv.

        Returns:
            True if weights were loaded successfully, False if fallback needed.
        """
        weights_file = self.weights_dir / "weights.csv"
        if not weights_file.exists():
            logger.warning(
                f"weights.csv missing at {self.weights_dir}, "
                "falling back to equal-weight top-K behavior"
            )
            return False

        # Check stale mtime
        mtime = weights_file.stat().st_mtime
        age_days = (time.time() - mtime) / (24 * 3600)
        if age_days > STALE_DAYS:
            logger.warning(
                f"weights stale ({age_days:.1f} days old, threshold={STALE_DAYS}), falling back"
            )
            return False

        # Load weights
        import polars as pl

        df = pl.read_csv(weights_file)
        self.weights = {}
        for row in df.iter_rows(named=True):
            self.weights[row["asset"]] = float(row["weight"])

        logger.info(
            f"loaded {len(self.weights)} optimized weights from {weights_file}, top_k={self.top_k}"
        )
        return True

    async def init(self) -> None:
        """Load model and initialize strategy state."""
        loaded = self._load_weights()
        if not loaded:
            self._fallback = True
            self.weights = None
            # Fall back: build equal-weight top-K from watchlist
            await self._init_fallback()

    async def _init_fallback(self) -> None:
        """Initialize fallback equal-weight top-K behavior."""
        logger.warning("weights.csv missing, falling back to equal-weight top-K behavior")
        # In fallback mode, we use the watchlist to get top-k equal weight
        # The actual fallback is LGBMTop20Strategy behavior
        fallback_config = {
            "top_k": self.top_k,
            "model_version": self.model_version,
            "watchlist": self.config.get("watchlist", []) if self.config else [],
        }
        self._fallback_strategy = LGBMTop20Strategy(self.broker, fallback_config)
        await self._fallback_strategy.init()
        logger.info("OptimizedTopKStrategy running in fallback (LGBMTop20Strategy) mode")

    def _trade_extra(self, weight: float) -> dict:
        """Build extra dict for trade_target_pct calls."""
        return {
            "reason": "optimized_topk",
            "weight": float(weight),
            "version": self.model_version,
        }

    async def on_day_open(self, tm: datetime) -> None:
        """Generate predictions and rebalance portfolio.

        Args:
            tm: Current datetime (date portion used as asof_date).
        """
        if self._fallback:
            if hasattr(self, "_fallback_strategy"):
                await self._fallback_strategy.on_day_open(tm)
            return

        if not self.weights:
            logger.warning("No weights loaded, skipping on_day_open")
            return

        # Sort by weight descending and take top-K
        sorted_assets = sorted(self.weights.items(), key=lambda x: x[1], reverse=True)[: self.top_k]

        target_assets = {asset for asset, _ in sorted_assets}
        weight_total = sum(w for _, w in sorted_assets)

        # Step 1: Clear positions not in target list first.
        # Selling first frees cash before rebalancing targets, avoiding
        # transient cash depletion when buys precede sells.
        for asset in list(self._position_cache.keys()):
            if asset not in target_assets:
                await self.broker.trade_target_pct(
                    asset=asset,
                    target_pct=0.0,
                    order_time=tm,
                )
                del self._position_cache[asset]

        # Step 2: Adjust target weights for residual cash.
        # trade_target_pct uses total_asset() (cash + market_value) as its
        # denominator. When cash > 0, the sum of position weights is less
        # than total_weight, causing perpetual buying pressure that drains
        # cash over consecutive trading days.  Scaling by market_value/total
        # anchors the allocation to the invested portion only.
        total = self.broker.total_asset()
        market_value = self.broker.market_value()
        cash_factor = market_value / total if total > 0 and market_value > 0 else 1.0

        # Step 3: Place orders for target positions
        for asset, weight in sorted_assets:
            adjusted_weight = float(weight) * cash_factor
            await self.broker.trade_target_pct(
                asset=asset,
                target_pct=adjusted_weight,
                order_time=tm,
            )
            self._position_cache[asset] = float(weight)

        logger.info(
            f"on_day_open {tm.date()}: targets={len(sorted_assets)}, "
            f"total_weight={weight_total:.4f}"
        )

    async def on_bar(self, tm: datetime, quote: dict | None = None, frame_type=None) -> None:
        """No-op for daily strategy."""

    async def on_day_close(self, tm: datetime) -> None:
        """No-op for daily strategy."""

    async def on_stop(self) -> None:
        """Release model references for garbage collection."""
        self.weights = None
        self._position_cache.clear()
        if hasattr(self, "_fallback_strategy"):
            await self._fallback_strategy.on_stop()
        logger.info("OptimizedTopKStrategy stopped")
