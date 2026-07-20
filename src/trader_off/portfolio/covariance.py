"""Covariance estimation using Ledoit-Wolf shrinkage or sample covariance (FR-3000).

Provides `estimate_covariance` for constructing a covariance matrix from
asset return DataFrames. Supports "sample" and "ledoit_wolf" methods.
"""

from typing import Literal

import numpy as np
import polars as pl
from loguru import logger
from sklearn.covariance import LedoitWolf

from trader_off.utils.exceptions import InsufficientDataError

_MIN_DAYS = 30


def estimate_covariance(
    returns_df: pl.DataFrame,
    method: Literal["sample", "ledoit_wolf"] = "ledoit_wolf",
) -> np.ndarray:
    """Estimate covariance matrix from asset returns.

    Args:
        returns_df: DataFrame with a ``date`` column and asset return columns.
            Each asset column contains daily returns (Float64).
        method: Estimation method — ``"sample"`` for empirical covariance or
            ``"ledoit_wolf"`` (default) for Ledoit-Wolf shrinkage.

    Returns:
        (N, N) covariance matrix as a numpy ndarray. Symmetric and
        positive-semidefinite.

    Raises:
        InsufficientDataError: If ``returns_df`` has fewer than 30 rows.
    """
    # Separate date column from asset columns
    asset_cols = [c for c in returns_df.columns if c != "date"]

    # Detect and drop columns that contain only NaN
    dropped: list[str] = []
    for col in asset_cols:
        if returns_df[col].null_count() == returns_df.height:
            dropped.append(col)

    if dropped:
        for col in dropped:
            logger.warning("Dropping asset with all-NaN returns: {}", col)
        asset_cols = [c for c in asset_cols if c not in dropped]

    n_obs = returns_df.height
    if n_obs < _MIN_DAYS:
        raise InsufficientDataError(f"need at least {_MIN_DAYS} days of returns, got {n_obs}")

    # Extract returns matrix
    returns_mat = returns_df.select(asset_cols).to_numpy()

    if method == "sample":
        cov = np.cov(returns_mat, rowvar=False)
    elif method == "ledoit_wolf":
        lw = LedoitWolf()
        lw.fit(returns_mat)
        cov = lw.covariance_
    else:
        raise ValueError(f"Unknown method: {method}")

    # Enforce symmetry
    cov = (cov + cov.T) / 2.0

    # Validate PSD: eigenvalues should be >= -tol
    tol = 1e-8
    eigvals = np.linalg.eigvalsh(cov)
    if np.any(eigvals < -tol):
        logger.warning(
            "Covariance matrix has negative eigenvalues (min={:e}); "
            "results may be numerically unstable",
            eigvals.min(),
        )

    return cov
