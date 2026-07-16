"""Prediction service (FR-0900).

Provides an async predict function that loads a trained model, fetches
historical data for a watchlist, computes features, and returns ranked scores.
"""

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import polars as pl
from loguru import logger

from trader_off.features.momentum import compute_momentum_features
from trader_off.features.volatility import compute_volatility_features
from trader_off.features.volume import compute_volume_features
from trader_off.training.serialize import load_model

if TYPE_CHECKING:
    from trader_off.data.loader import DataLoader

DEFAULT_LOOKBACK = 120


async def predict(
    model_version: str,
    watchlist: list[str],
    asof_date: date,
    data_loader: "DataLoader | None" = None,
    models_dir: Path | str = "models",
    skipped_path: Path | str | None = None,
) -> pl.DataFrame:
    """Generate ranked predictions for a watchlist of assets.

    Args:
        model_version: Version string identifying the model directory.
        watchlist: List of asset codes to score.
        asof_date: Reference date for prediction.
        data_loader: DataLoader instance for fetching history.
            If None, a default DataLoader is created.
        models_dir: Root directory for model storage.
        skipped_path: Path to write predict_skipped.json.
            Defaults to predictions_skipped_<date>.json.

    Returns:
        DataFrame with columns: asset, score, rank, sorted by score descending.
    """
    if data_loader is None:
        from trader_off.data.loader import DataLoader

        data_loader = DataLoader()

    # Load model
    artifact = load_model(version=model_version, models_dir=models_dir)
    booster = artifact.booster
    scaler = artifact.scaler
    feature_names = artifact.feature_names
    lookback = artifact.metadata.get("max_lookback", DEFAULT_LOOKBACK)

    results: list[dict] = []
    skipped: list[dict] = []

    for asset in watchlist:
        try:
            hist = await data_loader.get_history(
                asset=asset,
                end_date=asof_date,
                count=lookback,
            )
        except Exception as e:
            logger.warning(f"Skipping {asset}: data fetch failed ({e})")
            skipped.append({"asset": asset, "reason": f"fetch_failed: {e}"})
            continue

        if hist is None or len(hist) < lookback:
            logger.warning(f"Skipping {asset}: insufficient history "
                           f"({len(hist) if hist is not None else 0} < {lookback})")
            skipped.append({
                "asset": asset,
                "reason": "insufficient_history",
                "available_days": len(hist) if hist is not None else 0,
            })
            continue

        # Compute features
        feats_mom = compute_momentum_features(hist)
        feats_vol = compute_volatility_features(hist)
        feats_vol = feats_vol.drop([c for c in hist.columns if c in feats_vol.columns
                                    and c not in ("asset", "date")])
        # Merge features — take the latest row (asof_date)
        # All feature functions return the same DataFrame with added columns
        combined = (
            feats_mom
            .join(feats_vol.select(["asset", "date"] + [
                c for c in feats_vol.columns
                if c not in feats_mom.columns
            ]), on=["asset", "date"], how="left")
        )

        # Get volume features
        feats_vol2 = compute_volume_features(hist)
        combined = combined.join(
            feats_vol2.select(["asset", "date"] + [
                c for c in feats_vol2.columns
                if c not in combined.columns
            ]), on=["asset", "date"], how="left")

        # Take the last row (most recent date)
        latest = combined.sort("date").tail(1)

        # Extract feature values in the correct order
        feature_cols = [c for c in feature_names if c in latest.columns]
        if len(feature_cols) != len(feature_names):
            logger.warning(f"Feature mismatch for {asset}: "
                           f"expected {feature_names}, got {feature_cols}")
            # Filter to common columns
            feature_cols = [c for c in feature_names if c in feature_cols]

        # Get feature row as numpy
        feat_row = latest.select(feature_cols).to_numpy().astype(np.float64)

        # Handle NaN → fill with 0 (should have been handled by scaler, but safety)
        feat_row = np.nan_to_num(feat_row, nan=0.0)

        # Predict
        score = float(booster.predict(feat_row)[0])
        results.append({"asset": asset, "score": score})

    # Write skipped assets
    if skipped and skipped_path:
        skipped_path = Path(skipped_path)
        skipped_path.parent.mkdir(parents=True, exist_ok=True)
        skipped_path.write_text(json.dumps(skipped, indent=2))
        logger.info(f"Skipped assets written to {skipped_path}")

    # Build result DataFrame
    if not results:
        return pl.DataFrame(
            {"asset": [], "score": [], "rank": []},
            schema={"asset": pl.Utf8, "score": pl.Float64, "rank": pl.Int32},
        )

    result_df = pl.DataFrame(results)
    result_df = result_df.sort("score", descending=True)
    result_df = result_df.with_columns(
        pl.int_range(1, len(result_df) + 1, dtype=pl.Int32).alias("rank")
    )

    return result_df
