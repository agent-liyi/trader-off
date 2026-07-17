"""Expected returns input and asset alignment validation (FR-3100).

Provides `build_expected_returns` to convert prediction scores into an
{asset: mu} dictionary, and `validate_asset_alignment` to ensure the
assets in mu match those in the covariance matrix before optimization.
"""

from typing import Literal

import numpy as np
import polars as pl
from loguru import logger

from trader_off.utils.exceptions import AssetMismatchError


def build_expected_returns(
    predictions: pl.DataFrame,
    mode: Literal["raw", "zscore"] = "raw",
) -> dict[str, float]:
    """Build expected returns dictionary from prediction scores.

    Args:
        predictions: DataFrame with columns ``asset`` (str), ``score`` (float),
            and ``rank`` (int). Typically output from v0.1.0 predict.
        mode: ``"raw"`` returns original scores; ``"zscore"`` returns
            z-score normalized scores (zero mean, unit variance).

    Returns:
        Dict mapping each asset to its expected return (mu).

    Raises:
        ValueError: If any score value is NaN.
    """
    if predictions["score"].null_count() > 0:
        raise ValueError("NaN values found in prediction scores")

    assets = predictions["asset"].to_list()
    scores = predictions["score"].to_list()

    if mode == "raw":
        values = scores
    elif mode == "zscore":
        arr = np.array(scores, dtype=np.float64)
        mean = np.mean(arr)
        std = np.std(arr)
        if std < 1e-12:
            logger.warning("Score standard deviation near zero; zscore will be degenerate")
            std = 1.0
        values = ((arr - mean) / std).tolist()
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return dict(zip(assets, values))


def validate_asset_alignment(
    mu: dict[str, float],
    cov_assets: list[str],
) -> None:
    """Validate that mu assets match the covariance matrix assets.

    The covariance matrix may have dropped some assets (e.g., due to
    all-NaN returns). This function checks that every asset in ``cov_assets``
    exists in ``mu`` and raises an error if any are missing.

    Args:
        mu: Expected returns dictionary (asset -> return).
        cov_assets: List of asset tickers present in the covariance matrix.

    Raises:
        ValueError: If assets in ``mu`` are missing from ``cov_assets``
            or vice versa.
    """
    mu_set = set(mu.keys())
    cov_set = set(cov_assets)

    missing_from_cov = mu_set - cov_set
    missing_from_mu = cov_set - mu_set

    if missing_from_cov or missing_from_mu:
        parts = []
        if missing_from_cov:
            parts.append(f"assets in mu but missing from covariance: {sorted(missing_from_cov)}")
        if missing_from_mu:
            parts.append(f"assets in covariance but missing from mu: {sorted(missing_from_mu)}")
        msg = "missing assets: " + "; ".join(parts)
        raise AssetMismatchError(msg)
