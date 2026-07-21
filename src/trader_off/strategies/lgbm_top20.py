"""LGBMTop20Strategy (FR-1000).

A long-only Top-K equal-weight strategy driven by lightGBM model predictions.
Inherits from BaseStrategy (millionaire framework or compat shim).
"""

import math
from datetime import datetime

import polars as pl
from loguru import logger

from trader_off.strategies.compat import BaseStrategy


class LGBMTop20Strategy(BaseStrategy):
    """Top-20 equal-weight long-only strategy using lightGBM predictions.

    On each trading day (on_day_open), calls the predict service to get
    ranked scores for all assets in the universe, then adjusts portfolio
    to hold the top-K assets at equal weight.

    Attributes:
        model: Loaded ModelArtifact or Booster.
        model_version: Version string of the loaded model.
        top_k: Number of top assets to hold.
        min_score: Minimum score threshold for inclusion.
        watchlist: List of asset codes in the universe.
    """

    def __init__(self, broker, config: dict | None = None):
        """Initialize the strategy.

        Args:
            broker: Broker instance for order execution.
            config: Configuration dict with keys:
                - model_version (str): Required.
                - top_k (int): Default 20.
                - min_score (float): Default -inf.
                - watchlist (list[str]): Asset universe. If not provided,
                  derived from broker.
        """
        super().__init__(broker, config)
        config = config or {}

        self.model_version: str = config.get("model_version", "")
        self.top_k: int = int(config.get("top_k", 20))
        self.min_score: float = float(config.get("min_score", -float("inf")))
        self.watchlist: list[str] = config.get("watchlist", [])

        self.model = None
        self._position_cache: dict[str, float] = {}

    async def init(self) -> None:
        """Load model and initialize strategy state."""
        from trader_off.training.serialize import load_model

        artifact = load_model(version=self.model_version)
        self.model = artifact.booster
        logger.info(
            f"LGBMTop20Strategy initialized: "
            f"model={self.model_version}, top_k={self.top_k}, "
            f"min_score={self.min_score}"
        )

    async def on_day_open(self, tm: datetime) -> None:
        """Generate predictions and rebalance portfolio.

        Args:
            tm: Current datetime (date portion used as asof_date).
        """
        if not self.model:
            logger.error("Model not loaded, skipping on_day_open")
            return

        from trader_off.prediction.service import predict

        # Determine universe
        watchlist = self.watchlist
        if not watchlist:
            logger.warning("No watchlist configured, skipping predict")
            return

        # Call predict service
        predictions = await predict(
            model_version=self.model_version,
            watchlist=watchlist,
            asof_date=tm.date(),
        )

        if len(predictions) == 0:
            logger.warning("No predictions returned, skipping rebalance")
            return

        # Filter by rank ≤ top_k and score ≥ min_score
        targets = predictions.filter(
            (pl.col("rank") <= self.top_k) & (pl.col("score") >= self.min_score)
        )

        target_assets = set(targets["asset"].to_list())
        weight = 1.0 / self.top_k if self.top_k > 0 else 0.0

        # Snapshot pre-sell values BEFORE any trades.
        # Fix #2: cash_factor must use pre-sell snapshot to avoid drift.
        initial_total = self.broker.total_asset()
        initial_market_value = self.broker.market_value()

        try:
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

            # Step 2: Compute cash_factor from pre-sell snapshot with validation.
            cash_factor = self._compute_cash_factor(initial_market_value, initial_total)
            adjusted_weight = weight * cash_factor

            # Step 3: Place orders for target positions
            for row in targets.iter_rows(named=True):
                await self.broker.trade_target_pct(
                    asset=row["asset"],
                    target_pct=adjusted_weight,
                    order_time=tm,
                )
                self._position_cache[row["asset"]] = weight

            logger.info(f"on_day_open {tm.date()}: targets={len(targets)}, weight={weight:.4f}")
        finally:
            # Fix #1: Reconcile _position_cache with broker.positions after
            # each rebalance cycle. Full atomicity deferred to v0.4.x.
            self._reconcile_position_cache()

    def _compute_cash_factor(self, market_value: float, total: float) -> float:
        """Compute cash factor with range validation.

        Args:
            market_value: Total market value of all positions.
            total: Total portfolio value (cash + market_value).

        Returns:
            cash_factor in range [0, 1]; falls back to 1.0 if invalid.
        """
        if total > 0 and market_value > 0:
            raw = market_value / total
            if math.isfinite(raw) and 0.0 <= raw <= 1.0:
                return raw
            logger.warning(
                f"Invalid cash_factor={raw:.6f} (mv={market_value:.2f}, total={total:.2f}), "
                "falling back to 1.0"
            )
        return 1.0

    def _reconcile_position_cache(self) -> None:
        """Reconcile _position_cache with broker.positions after rebalance.

        Removes entries from cache that are not present in broker.positions,
        logging discrepancies as warnings. Full atomicity deferred to v0.4.x.
        """
        broker_positions = self.broker.positions
        if not isinstance(broker_positions, dict):
            return
        for asset in list(self._position_cache.keys()):
            if asset not in broker_positions:
                logger.warning(
                    f"Position cache discrepancy: '{asset}' in cache but not in "
                    "broker.positions, removing from cache"
                )
                del self._position_cache[asset]

    async def on_bar(self, tm: datetime, quote: dict | None = None, frame_type=None) -> None:
        """No-op for daily strategy."""

    async def on_day_close(self, tm: datetime) -> None:
        """No-op for daily strategy."""

    async def on_stop(self) -> None:
        """Release model references for garbage collection."""
        self.model = None
        self._position_cache.clear()
        logger.info("LGBMTop20Strategy stopped")
