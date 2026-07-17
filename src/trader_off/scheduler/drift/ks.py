"""KS (Kolmogorov-Smirnov) drift detection — FR-1800.

Computes the two-sample KS statistic and p-value using
scipy.stats.ks_2samp. Provides per-feature batch detection
and a convenience wrapper that returns DriftResult.

Algorithm:
    1. Drop non-finite values from input arrays.
    2. Call scipy.stats.ks_2samp(baseline, current).
    3. Return p-value, KS statistic, or structured DriftResult.
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl
from scipy import stats

from trader_off.scheduler.drift.result import DriftResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_ks_pvalue(baseline: np.ndarray, current: np.ndarray) -> float:
    """Compute the two-sample KS test p-value between baseline and current.

    Uses scipy.stats.ks_2samp as the reference implementation. The null
    hypothesis is that the two samples are drawn from the same continuous
    distribution.

    Args:
        baseline: 1-D numpy array of reference values.
        current: 1-D numpy array of current values.

    Returns:
        Two-sided p-value in [0, 1]. Low p-values indicate the two
        distributions are significantly different.

    Raises:
        ValueError: If either array contains no finite values after
            dropping NaN/Inf.
    """
    baseline = baseline[np.isfinite(baseline)]
    current = current[np.isfinite(current)]

    if len(baseline) == 0 or len(current) == 0:
        raise ValueError("Input arrays must contain at least one finite value")

    result = stats.ks_2samp(baseline, current)
    return float(result.pvalue)


def compute_feature_ks(
    baseline_df: pl.DataFrame,
    current_df: pl.DataFrame,
    feature_cols: list[str],
    *,
    threshold: float = 0.05,
) -> pl.DataFrame:
    """Compute KS statistic and p-value for each feature column.

    For features where the baseline or current has no finite samples,
    returns (ks_statistic=0.0, p_value=1.0, is_drift=False) and logs
    a WARNING.

    Args:
        baseline_df: Polars DataFrame with reference data.
        current_df: Polars DataFrame with current data (same schema).
        feature_cols: List of feature column names to compute KS for.
        threshold: P-value threshold below which is_drift is True
            (default 0.05).

    Returns:
        Polars DataFrame with columns: feature (str), ks_statistic
        (float64), p_value (float64), is_drift (bool).
    """
    results: list[dict] = []

    for col in feature_cols:
        baseline_series = baseline_df[col]
        current_series = current_df[col]

        # Extract finite values to numpy arrays
        baseline_np = baseline_series.drop_nulls().to_numpy()
        baseline_np = baseline_np[np.isfinite(baseline_np)]
        current_np = current_series.drop_nulls().to_numpy()
        current_np = current_np[np.isfinite(current_np)]

        # Handle NaN / empty cases
        if len(baseline_np) == 0:
            logger.warning("feature %s has no samples in baseline window", col)
            results.append(
                {
                    "feature": col,
                    "ks_statistic": 0.0,
                    "p_value": 1.0,
                    "is_drift": False,
                }
            )
            continue

        if len(current_np) == 0:
            logger.warning("feature %s has no samples in current window", col)
            results.append(
                {
                    "feature": col,
                    "ks_statistic": 0.0,
                    "p_value": 1.0,
                    "is_drift": False,
                }
            )
            continue

        # Compute KS test
        ks_result = stats.ks_2samp(baseline_np, current_np)
        p_value = float(ks_result.pvalue)
        ks_stat = float(ks_result.statistic)

        results.append(
            {
                "feature": col,
                "ks_statistic": ks_stat,
                "p_value": p_value,
                "is_drift": p_value < threshold,
            }
        )

    return pl.DataFrame(
        results,
        schema={
            "feature": pl.Utf8,
            "ks_statistic": pl.Float64,
            "p_value": pl.Float64,
            "is_drift": pl.Boolean,
        },
    )


def detect_ks(
    reference: np.ndarray,
    current: np.ndarray,
    *,
    threshold: float = 0.05,
) -> DriftResult:
    """Detect drift using KS two-sample test.

    Convenience wrapper around scipy.stats.ks_2samp that returns a
    structured DriftResult with threshold comparison.

    Args:
        reference: 1-D numpy array of reference values.
        current: 1-D numpy array of current values.
        threshold: P-value threshold for drift detection (default 0.05).
            Drift is detected when p_value < threshold.

    Returns:
        DriftResult with method="ks", score=KS_statistic, threshold,
        is_drift=p_value < threshold, and empty bin_edges (KS does not
        use binning).
    """
    reference = reference[np.isfinite(reference)]
    current = current[np.isfinite(current)]

    if len(reference) == 0 or len(current) == 0:
        raise ValueError("Input arrays must contain at least one finite value")

    ks_result = stats.ks_2samp(reference, current)
    statistic = float(ks_result.statistic)
    p_value = float(ks_result.pvalue)

    return DriftResult(
        method="ks",
        score=statistic,
        threshold=threshold,
        is_drift=p_value < threshold,
        bin_edges=[],
    )
