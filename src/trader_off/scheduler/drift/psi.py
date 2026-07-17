"""PSI (Population Stability Index) drift detection — FR-1700.

Calculates PSI between reference and current distributions using
quantile-based binning with zero-bin epsilon smoothing.

Algorithm:
    1. Compute n_bins quantile-based bin edges from the reference distribution.
    2. Bin both reference and current data into those bins.
    3. Compute proportions p_i (reference) and q_i (current) for each bin.
    4. For bins where p_i == 0 or q_i == 0, apply epsilon smoothing.
    5. PSI = sum((p_i - q_i) * ln(p_i / q_i)) for all bins.
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

from trader_off.scheduler.drift.result import DriftResult

logger = logging.getLogger(__name__)


def _quantile_bin_edges(reference: np.ndarray, n_bins: int) -> np.ndarray:
    """Compute quantile-based bin edges from the reference distribution.

    Returns n_bins + 1 edges spanning from slightly below the min to
    slightly above the max so that all data falls into the [1, n_bins] range
    when digitized.

    Args:
        reference: 1-D array of reference values (must be finite).
        n_bins: Number of bins (≥ 1).

    Returns:
        Array of n_bins + 1 bin edges.
    """
    edges = np.quantile(reference, np.linspace(0, 1, n_bins + 1))
    # Ensure strict monotonicity: when the reference has tied quantile
    # edges (e.g. many identical values), push each edge slightly past
    # its predecessor so np.digitize receives a valid monotonic sequence.
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = np.nextafter(edges[i - 1], edges[i - 1] + 1)
    edges[0] -= 1e-10
    edges[-1] += 1e-10
    return edges


def _bin_proportions(values: np.ndarray, edges: np.ndarray, n_bins: int) -> np.ndarray:
    """Compute per-bin proportions for the given values.

    Args:
        values: 1-D array of values to bin.
        edges: Bin edges from _quantile_bin_edges.
        n_bins: Number of bins.

    Returns:
        Array of length n_bins with proportions summing to 1.
    """
    bins = np.digitize(values, edges)
    counts = np.bincount(bins, minlength=n_bins + 2)
    # bins are indexed 0..n_bins+1; we want indices 1..n_bins
    bin_counts = counts[1 : n_bins + 1].astype(np.float64)
    return bin_counts / bin_counts.sum()


def _psi_from_proportions(p: np.ndarray, q: np.ndarray, epsilon: float) -> float:
    """Compute PSI from per-bin proportions with epsilon smoothing.

    Args:
        p: Reference proportions (length n_bins).
        q: Current proportions (length n_bins).
        epsilon: Small constant to replace zero proportions.

    Returns:
        PSI score (non-negative float).
    """
    # Smooth zero bins
    p_smoothed = np.where(p == 0, epsilon, p)
    q_smoothed = np.where(q == 0, epsilon, q)

    # Re-normalize so proportions still sum to ~1
    p_smoothed = p_smoothed / p_smoothed.sum()
    q_smoothed = q_smoothed / q_smoothed.sum()

    # PSI = sum((p_i - q_i) * ln(p_i / q_i))
    psi = np.sum((p_smoothed - q_smoothed) * np.log(p_smoothed / q_smoothed))
    return float(max(psi, 0.0))  # Clamp to non-negative for numerical safety


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_psi(
    baseline: np.ndarray,
    current: np.ndarray,
    n_bins: int = 10,
    epsilon: float = 1e-6,
) -> float:
    """Compute the Population Stability Index (PSI) between two distributions.

    Uses quantile-based binning from the baseline distribution. Handles
    zero bins by replacing zero proportions with epsilon and re-normalizing.

    Args:
        baseline: 1-D numpy array of reference values (must be finite).
        current: 1-D numpy array of current values (must be finite).
        n_bins: Number of quantile bins (default 10).
        epsilon: Small constant used to smooth zero proportions (default 1e-6).

    Returns:
        PSI score as a non-negative float. 0.0 means identical distributions.

    Raises:
        ValueError: If n_bins < 1 or if arrays contain no finite values.
    """
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")

    # Drop non-finite values
    baseline = baseline[np.isfinite(baseline)]
    current = current[np.isfinite(current)]

    if len(baseline) == 0 or len(current) == 0:
        raise ValueError("Input arrays must contain at least one finite value")

    # Degenerate case: all baseline values identical → zero variance,
    # quantile bins collapse. PSI is 0 (no distribution to compare).
    if np.allclose(baseline, baseline[0]):
        return 0.0

    edges = _quantile_bin_edges(baseline, n_bins)
    p = _bin_proportions(baseline, edges, n_bins)
    q = _bin_proportions(current, edges, n_bins)

    return _psi_from_proportions(p, q, epsilon)


def compute_feature_psi(
    baseline_df: pl.DataFrame,
    current_df: pl.DataFrame,
    feature_cols: list[str],
    *,
    n_bins: int = 10,
    epsilon: float = 1e-6,
    threshold: float = 0.2,
) -> pl.DataFrame:
    """Compute PSI for each feature column between baseline and current DataFrames.

    For features where all current values are NaN, returns psi=0.0 and
    is_drift=False, logging a WARNING.

    Args:
        baseline_df: Polars DataFrame with reference data (rows × features).
        current_df: Polars DataFrame with current data (same schema).
        feature_cols: List of feature column names to compute PSI for.
        n_bins: Number of quantile bins per feature (default 10).
        epsilon: Epsilon for zero-bin smoothing (default 1e-6).
        threshold: PSI threshold above which is_drift is True (default 0.2).

    Returns:
        Polars DataFrame with columns: feature (str), psi (float64),
        is_drift (bool).
    """
    results: list[dict] = []

    for col in feature_cols:
        baseline_series = baseline_df[col]
        current_series = current_df[col]

        # Extract finite values to numpy arrays (polars treats NaN
        # as valid float64, not null, so we filter both nulls and nans).
        baseline_np = baseline_series.drop_nulls().to_numpy()
        baseline_np = baseline_np[np.isfinite(baseline_np)]
        current_np = current_series.drop_nulls().to_numpy()
        current_np = current_np[np.isfinite(current_np)]

        if len(current_np) == 0:
            logger.warning("feature %s has no samples in current window", col)
            results.append(
                {
                    "feature": col,
                    "psi": 0.0,
                    "is_drift": False,
                }
            )
            continue

        if len(baseline_np) == 0:
            logger.warning("feature %s has no samples in baseline window", col)
            results.append(
                {
                    "feature": col,
                    "psi": 0.0,
                    "is_drift": False,
                }
            )
            continue

        psi = compute_psi(baseline_np, current_np, n_bins=n_bins, epsilon=epsilon)
        results.append(
            {
                "feature": col,
                "psi": psi,
                "is_drift": psi > threshold,
            }
        )

    return pl.DataFrame(
        results,
        schema={"feature": pl.Utf8, "psi": pl.Float64, "is_drift": pl.Boolean},
    )


def detect_psi(
    reference: np.ndarray,
    current: np.ndarray,
    *,
    n_bins: int = 10,
    threshold: float = 0.2,
    epsilon: float = 1e-6,
) -> DriftResult:
    """Detect drift using PSI between reference and current distributions.

    Convenience wrapper around compute_psi that returns a structured
    DriftResult with threshold comparison.

    Args:
        reference: 1-D numpy array of reference values.
        current: 1-D numpy array of current values.
        n_bins: Number of quantile bins (default 10).
        threshold: PSI threshold for drift detection (default 0.2).
        epsilon: Epsilon for zero-bin smoothing (default 1e-6).

    Returns:
        DriftResult with method="psi", score, threshold, is_drift,
        and bin_edges used for computation.
    """
    edges = _quantile_bin_edges(reference, n_bins)
    score = compute_psi(reference, current, n_bins=n_bins, epsilon=epsilon)
    return DriftResult(
        method="psi",
        score=score,
        threshold=threshold,
        is_drift=score > threshold,
        bin_edges=edges.tolist(),
    )
