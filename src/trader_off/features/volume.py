"""Volume feature computation (FR-0300).

Computes N-day average turnover and volume-price correlation:
- turnover_N = mean(turnover, N)
- vp_corr_N = rolling_corr(volume, close, N)
for N in {5, 10, 20}.
"""

import polars as pl
from loguru import logger


def _get_assets_with_missing_turnover(ohlcv_df: pl.DataFrame) -> list[str]:
    """Identify assets where turnover column is entirely NaN."""
    missing = []
    for asset in ohlcv_df["asset"].unique().to_list():
        asset_data = ohlcv_df.filter(pl.col("asset") == asset)
        if asset_data["turnover"].null_count() == len(asset_data):
            missing.append(asset)
            logger.warning(f"turnover missing for asset={asset}, "
                           "all volume columns will be NaN")
    return missing


def compute_volume_features(ohlcv_df: pl.DataFrame) -> pl.DataFrame:
    """Compute volume-based features from daily OHLCV data grouped by asset.

    Args:
        ohlcv_df: DataFrame with columns asset, date, close, volume, turnover.

    Returns:
        DataFrame with original columns plus turnover_5/10/20 and
        vp_corr_5/10/20 (all Float64). Assets with all-NaN turnover
        get NaN for all volume columns with a WARNING log.
    """
    periods = [5, 10, 20]
    result = ohlcv_df.sort(["asset", "date"])

    # Identify assets with missing turnover
    missing_assets = _get_assets_with_missing_turnover(result)

    for n in periods:
        # Average turnover
        result = result.with_columns(
            pl.col("turnover")
            .rolling_mean(window_size=n, min_samples=n)
            .over("asset")
            .alias(f"turnover_{n}")
        )

        # Volume-price correlation
        result = result.with_columns(
            pl.rolling_corr(
                pl.col("volume"),
                pl.col("close"),
                window_size=n,
                min_samples=n,
            )
            .over("asset")
            .alias(f"vp_corr_{n}")
        )

    # For assets with all-NaN turnover, nullify vp_corr columns as well
    if missing_assets:
        vp_cols = [f"vp_corr_{n}" for n in periods]
        result = result.with_columns(
            pl.when(pl.col("asset").is_in(missing_assets))
            .then(pl.lit(None, dtype=pl.Float64))
            .otherwise(pl.col(col))
            .alias(col)
            for col in vp_cols
        )

    return result
