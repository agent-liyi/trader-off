"""LGBMTop20Strategy (FR-1000).

A long-only Top-K equal-weight strategy driven by lightGBM model predictions.
Inherits from BaseStrategy (millionaire framework or compat shim).
"""

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

        # Place orders for target positions
        for row in targets.iter_rows(named=True):
            extra = {
                "reason": "lgbm_top20",
                "score": row["score"],
                "rank": row["rank"],
                "model_version": self.model_version,
            }
            self.broker.trade_target_pct(
                asset=row["asset"],
                target_pct=weight,
                extra=extra,
            )
            self._position_cache[row["asset"]] = weight

        # Clear positions not in target list
        for asset in list(self._position_cache.keys()):
            if asset not in target_assets:
                self.broker.trade_target_pct(
                    asset=asset,
                    target_pct=0.0,
                    extra={
                        "reason": "lgbm_top20",
                        "score": 0.0,
                        "rank": 0,
                        "model_version": self.model_version,
                    },
                )
                del self._position_cache[asset]

        logger.info(f"on_day_open {tm.date()}: targets={len(targets)}, weight={weight:.4f}")

    async def on_bar(self, tm: datetime) -> None:
        """No-op for daily strategy."""

    async def on_day_close(self, tm: datetime) -> None:
        """No-op for daily strategy."""

    async def on_stop(self) -> None:
        """Release model references for garbage collection."""
        self.model = None
        self._position_cache.clear()
        logger.info("LGBMTop20Strategy stopped")
