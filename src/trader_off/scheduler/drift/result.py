"""Dataclasses for drift detection results.

FR-1700: PSI drift detection result type.
FR-2600: DriftDecision for combined PSI+KS orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import polars as pl


@dataclass(frozen=True)
class DriftResult:
    """Result of a single drift detection method.

    Fields:
        method: The detection method used (e.g. "psi", "ks").
        score: The computed drift score (PSI value, KS statistic, etc.).
        threshold: The threshold used to determine drift.
        is_drift: Whether the score exceeds the threshold.
        bin_edges: Bin edges used for computation (n_bins + 1 edges for PSI).
    """

    method: Literal["psi", "ks"]
    score: float
    threshold: float
    is_drift: bool
    bin_edges: list[float]


@dataclass(frozen=True)
class DriftDecision:
    """Orchestrated drift evaluation decision (FR-2600).

    Combines PSI and KS per-feature statistics into a retrain decision
    with a severity level (ok, light_drift, moderate_drift, strong_drift).

    Per interfaces.md §1.6.

    Fields:
        should_retrain: Whether retraining is recommended.
        reason: Severity level — one of ok, light_drift, moderate_drift, strong_drift.
        suggested_mode: Retraining mode if triggered (full or incremental).
        per_feature_stats: Merged per-feature PSI + KS statistics DataFrame
            with columns: feature, psi, ks_statistic, p_value.
    """

    should_retrain: bool
    reason: Literal["ok", "light_drift", "moderate_drift", "strong_drift"]
    suggested_mode: Literal["full", "incremental"]
    per_feature_stats: pl.DataFrame  # type: ignore[valid-type]
