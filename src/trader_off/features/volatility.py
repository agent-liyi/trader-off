"""Volatility feature computation (FR-0200).

Computes N-day realized volatility from daily OHLCV data:
vol_N = std(daily_returns, N) where daily_returns = close[t] / close[t-1] - 1.
"""

import polars as pl


def compute_volatility_features(ohlcv_df: pl.DataFrame) -> pl.DataFrame:
    """Compute volatility features from daily OHLCV data grouped by asset.

    Args:
        ohlcv_df: DataFrame with columns asset, date, open, high, low, close,
                  volume, turnover, adj_factor.

    Returns:
        DataFrame with original columns plus vol_10, vol_20, vol_60 (all Float64).
        Uses rolling std with min_periods=N, so first N-1 daily returns are NaN.
    """
    periods = [10, 20, 60]
    result = ohlcv_df.sort(["asset", "date"])

    # Compute daily returns: close[t] / close[t-1] - 1
    result = result.with_columns(
        (pl.col("close") / pl.col("close").shift(1) - 1.0)
        .over("asset")
        .alias("daily_return")
    )

    for n in periods:
        col_name = f"vol_{n}"
        result = result.with_columns(
            pl.col("daily_return")
            .rolling_std(window_size=n, min_samples=n)
            .over("asset")
            .alias(col_name)
        )

    # Drop intermediate daily_return column
    result = result.drop("daily_return")

    return result
