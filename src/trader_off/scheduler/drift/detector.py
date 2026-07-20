"""DriftDetector — orchestrates PSI + KS into a retrain decision (FR-2600).

Per interfaces.md §3.11:
- Combines per-feature PSI and KS statistics into a DriftDecision.
- Priority: strong_drift > moderate_drift > light_drift > ok.
- Light drift does NOT trigger retraining; moderate → incremental; strong → full.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

import polars as pl

from trader_off.scheduler.drift.result import DriftDecision

if TYPE_CHECKING:
    from trader_off.scheduler.core import SchedulerConfig

logger = logging.getLogger(__name__)

# Threshold for "light" PSI drift — features above this are counted but
# only trigger retraining when coupled with moderate/strong conditions.
_PSI_LIGHT_THRESHOLD: float = 0.1


class DriftDetector:
    """Orchestrate PSI and KS drift detection into a single retrain decision.

    Per interfaces.md §3.11.  Evaluates per-feature statistics from PSI
    and KS methods and applies priority rules to produce a DriftDecision.

    Args:
        config: SchedulerConfig with drift thresholds (psi_threshold,
            ks_pvalue_threshold, psi_strong, min_drift_features_incremental,
            min_drift_features_full).
        psi_fn: Callable for per-feature PSI computation.  Defaults to
            compute_feature_psi.  Injectable for testing.
        ks_fn: Callable for per-feature KS computation.  Defaults to
            compute_feature_ks.  Injectable for testing.
        baseline_df: Reference feature DataFrame (optional — needed when
            psi_fn/ks_fn require real data).
        current_df: Current feature DataFrame.
        feature_cols: List of feature column names.
    """

    def __init__(
        self,
        config: SchedulerConfig,
        psi_fn: Callable[..., pl.DataFrame] | None = None,
        ks_fn: Callable[..., pl.DataFrame] | None = None,
        *,
        baseline_df: pl.DataFrame | None = None,
        current_df: pl.DataFrame | None = None,
        feature_cols: list[str] | None = None,
    ) -> None:
        from trader_off.scheduler.drift.ks import compute_feature_ks
        from trader_off.scheduler.drift.psi import compute_feature_psi

        self._config = config
        self._psi_fn = psi_fn or compute_feature_psi
        self._ks_fn = ks_fn or compute_feature_ks
        self._baseline_df = baseline_df or pl.DataFrame()
        self._current_df = current_df or pl.DataFrame()
        self._feature_cols = feature_cols or []

    # ------------------------------------------------------------------
    # evaluate — public entry point
    # ------------------------------------------------------------------

    def evaluate(self) -> DriftDecision:
        """Run drift detection and return a DriftDecision.

        Steps:
        1. Compute per-feature PSI and KS DataFrames.
        2. Merge into a single per_feature_stats DataFrame.
        3. Apply priority rules to determine should_retrain, reason, mode.

        Returns:
            DriftDecision with should_retrain, reason, suggested_mode,
            and per_feature_stats.
        """
        psi_df = self._psi_fn(self._baseline_df, self._current_df, self._feature_cols)
        ks_df = self._ks_fn(self._baseline_df, self._current_df, self._feature_cols)

        # Merge per-feature stats
        per_feature_stats = _merge_stats(psi_df, ks_df)

        # Apply decision rules (priority: strong → moderate → light → ok)
        should_retrain, reason, suggested_mode = _decide(
            per_feature_stats,
            psi_threshold=self._config.psi_threshold,
            psi_strong=self._config.psi_strong,
            ks_pvalue_threshold=self._config.ks_pvalue_threshold,
            min_incr=self._config.min_drift_features_incremental,
            min_full=self._config.min_drift_features_full,
        )

        return DriftDecision(
            should_retrain=should_retrain,
            reason=reason,
            suggested_mode=suggested_mode,
            per_feature_stats=per_feature_stats,
        )


# ---------------------------------------------------------------------------
# Merge PSI and KS DataFrames
# ---------------------------------------------------------------------------


def _merge_stats(psi_df: pl.DataFrame, ks_df: pl.DataFrame) -> pl.DataFrame:
    """Merge PSI and KS per-feature DataFrames on the 'feature' column.

    Args:
        psi_df: DataFrame with columns feature, psi, is_drift.
        ks_df: DataFrame with columns feature, ks_statistic, p_value, is_drift.

    Returns:
        Merged DataFrame with columns: feature, psi, ks_statistic, p_value.
    """
    # Drop is_drift from KS side to avoid column conflict
    ks_clean = ks_df.select(["feature", "ks_statistic", "p_value"])
    return psi_df.join(ks_clean, on="feature", how="full")


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


_DriftReason = Literal["ok", "light_drift", "moderate_drift", "strong_drift"]
_RetrainMode = Literal["full", "incremental"]


def _decide(
    per_feature_stats: pl.DataFrame,
    *,
    psi_threshold: float,
    psi_strong: float,
    ks_pvalue_threshold: float,
    min_incr: int,
    min_full: int,
) -> tuple[bool, _DriftReason, _RetrainMode]:
    """Apply priority rules to produce (should_retrain, reason, suggested_mode).

    Priority order (highest first):

    1. **Strong drift** (→ full retrain):
       count of features with PSI > psi_strong >= min_full.

    2. **Moderate drift** (→ incremental retrain):
       count of features with PSI > psi_threshold >= 1
       OR count of features with KS p_value < ks_pvalue_threshold >= min_incr.

    3. **Light drift** (→ no retrain, warn):
       count of features with PSI > 0.1 in [min_full, min_incr)
       AND count of features with KS p_value < ks_pvalue_threshold < min_incr.

    4. **Ok** (→ no retrain).

    Args:
        per_feature_stats: Merged DataFrame with psi and p_value columns.
        psi_threshold: Moderate PSI threshold (default 0.2).
        psi_strong: Strong PSI threshold (default 0.5).
        ks_pvalue_threshold: KS p-value threshold (default 0.05).
        min_incr: Min drifted features for incremental (default 5).
        min_full: Min drifted features for full (default 3).

    Returns:
        Tuple of (should_retrain: bool, reason: str, suggested_mode: str).
    """
    psi_col = per_feature_stats["psi"]
    pvalue_col = per_feature_stats["p_value"]

    n_psi_strong = int((psi_col > psi_strong).sum())
    n_psi_moderate = int((psi_col > psi_threshold).sum())
    n_psi_light = int((psi_col > _PSI_LIGHT_THRESHOLD).sum())
    n_ks_drift = int((pvalue_col < ks_pvalue_threshold).sum())

    # 1. Strong
    if n_psi_strong >= min_full:
        return True, "strong_drift", "full"

    # 2. Moderate
    if n_psi_moderate >= 1 or n_ks_drift >= min_incr:
        return True, "moderate_drift", "incremental"

    # 3. Light
    if min_full <= n_psi_light < min_incr and n_ks_drift < min_incr:
        return False, "light_drift", "incremental"

    # 4. Ok
    return False, "ok", "full"
