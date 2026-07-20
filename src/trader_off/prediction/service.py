"""Prediction service (FR-0900).

Provides an async predict function that loads a trained model, fetches
historical data for a watchlist, computes features, and returns ranked scores.
"""

import asyncio
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

    # -------------------------------------------------------------------------
    # Step 1: Batch-fetch all histories concurrently
    # -------------------------------------------------------------------------
    fetched: list[tuple[str, pl.DataFrame | None, str | None]] = []
    histories_raw: list[pl.DataFrame] = []
    valid_assets: list[str] = []

    fetch_tasks = [
        data_loader.get_history(asset=asset, end_date=asof_date, count=lookback)
        for asset in watchlist
    ]
    results_fetch = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    for asset, result in zip(watchlist, results_fetch):
        if isinstance(result, Exception):
            logger.warning(f"Skipping {asset}: data fetch failed ({result})")
            fetched.append((asset, None, f"fetch_failed: {result}"))
            continue

        hist: pl.DataFrame = result  # type: ignore[assignment]
        if hist is None or len(hist) < lookback:
            logger.warning(
                f"Skipping {asset}: insufficient history "
                f"({len(hist) if hist is not None else 0} < {lookback})"
            )
            fetched.append(
                (
                    asset,
                    None,
                    "insufficient_history",
                )
            )
            continue

        histories_raw.append(hist)
        valid_assets.append(asset)

    # -------------------------------------------------------------------------
    # Step 2: Batch feature computation on concatenated DataFrame
    # -------------------------------------------------------------------------
    if histories_raw:
        combined = pl.concat(histories_raw, rechunk=True)
        combined = compute_momentum_features(combined)
        combined = compute_volatility_features(combined)
        combined = compute_volume_features(combined)

        # Extract latest row per asset (one pass, vectorized)
        latest_df = combined.sort(["asset", "date"]).group_by("asset", maintain_order=True).last()

        # Build feature matrix for all valid assets in one shot
        feat_matrix = np.zeros((len(valid_assets), len(feature_names)), dtype=np.float64)
        scaler_means: list[float] = []
        scaler_stds: list[float] = []

        for i, fname in enumerate(feature_names):
            scaler_means.append(scaler.mean_.get(fname, 0.0))
            std = scaler.std_.get(fname, 1.0)
            scaler_stds.append(1.0 if std == 0.0 else std)

        for i, asset in enumerate(valid_assets):
            asset_row = latest_df.filter(pl.col("asset") == asset).to_dicts()
            if not asset_row:
                feat_matrix[i, :] = 0.0
                continue

            row = asset_row[0]
            for j, fname in enumerate(feature_names):
                raw = row.get(fname)
                if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                    raw = 0.0
                    logger.warning(f"Feature '{fname}' missing for {asset}")
                z = (raw - scaler_means[j]) / scaler_stds[j]
                feat_matrix[i, j] = z

        # -------------------------------------------------------------------------
        # Step 3: Batch prediction (single booster.predict call)
        # -------------------------------------------------------------------------
        scores = booster.predict(feat_matrix)
        results = [
            {"asset": asset, "score": float(score)} for asset, score in zip(valid_assets, scores)
        ]
    else:
        results = []

    # -------------------------------------------------------------------------
    # Collect skipped assets
    # -------------------------------------------------------------------------
    skipped = [{"asset": asset, "reason": reason} for asset, _, reason in fetched]

    if skipped and skipped_path:
        skipped_path = Path(skipped_path)
        skipped_path.parent.mkdir(parents=True, exist_ok=True)
        skipped_path.write_text(json.dumps(skipped, indent=2))
        logger.info(f"Skipped assets written to {skipped_path}")

    # -------------------------------------------------------------------------
    # Build result DataFrame
    # -------------------------------------------------------------------------
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
