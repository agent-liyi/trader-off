"""Momentum feature computation (FR-0100).

Computes N-day price momentum features from daily OHLCV data:
ret_N = close[t] / close[t-N] - 1 for N in {5, 10, 20, 60}.
"""

import polars as pl


def compute_momentum_features(ohlcv_df: pl.DataFrame) -> pl.DataFrame:
    """Compute momentum features from daily OHLCV data grouped by asset.

    Args:
        ohlcv_df: DataFrame with columns asset, date, open, high, low, close,
                  volume, turnover, adj_factor. Must contain at minimum asset
                  and close columns.

    Returns:
        DataFrame with original columns plus ret_5, ret_10, ret_20, ret_60
        (all Float64). NaN values (e.g. insufficient history) are preserved as NaN.
    """
    periods = [5, 10, 20, 60]
    result = ohlcv_df.sort(["asset", "date"])

    for n in periods:
        col_name = f"ret_{n}"
        result = result.with_columns(
            (pl.col("close") / pl.col("close").shift(n) - 1.0)
            .over("asset")
            .alias(col_name)
        )

    return result
