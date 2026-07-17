"""Factor selection — Top-K + Pearson deduplication (FR-0400).

Selects the best factors by ICIR descending, greedily removing factors
whose IC time series have high absolute Pearson correlation with already-
selected factors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from trader_off.factor_mining.evaluation import FactorEvaluation
from trader_off.factor_mining.expression import FactorSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelectionDiagnostics:
    """Diagnostics from the factor selection process.

    Attributes:
        removed_by_redundancy: Factor ids removed due to high Pearson
            correlation with already-selected factors.
        final_k: Number of factors in the final selection.
        top_k_requested: The ``top_k`` value requested by the caller.
    """

    removed_by_redundancy: list[str]
    final_k: int
    top_k_requested: int


def select_factors(
    evaluations: list[FactorEvaluation],
    factor_specs: list[FactorSpec],
    top_k: int = 30,
    corr_threshold: float = 0.9,
) -> tuple[list[FactorSpec], SelectionDiagnostics]:
    """Select up to ``top_k`` factors by ICIR, removing redundant ones.

    Algorithm:
        1. Pair evaluations with their FactorSpecs (by list index).
        2. Sort by ``icir`` descending; ties broken by ``id`` ascending.
        3. Take the first ``top_k`` (or all if fewer than ``top_k``).
        4. Greedily iterate the candidates: keep a factor if its absolute
           Pearson correlation on the daily IC time series with all
           already-kept factors is below ``corr_threshold``.

    Args:
        evaluations: FactorEvaluation instances, one per candidate factor.
        factor_specs: FactorSpec instances, paired 1:1 with ``evaluations``.
        top_k: Maximum number of factors to select.
        corr_threshold: Maximum allowed absolute Pearson correlation between
            a candidate and any already-selected factor. Factors whose
            |Pearson| >= this threshold are removed.

    Returns:
        A tuple of ``(selected_specs, diagnostics)``. ``selected_specs``
        is sorted by ICIR descending.

    Raises:
        ValueError: If ``evaluations`` and ``factor_specs`` have different
            lengths.
    """
    if len(evaluations) != len(factor_specs):
        raise ValueError(
            f"evaluations and factor_specs must have the same length, "
            f"got {len(evaluations)} and {len(factor_specs)}"
        )

    if not evaluations:
        return [], SelectionDiagnostics(
            removed_by_redundancy=[],
            final_k=0,
            top_k_requested=top_k,
        )

    # Pair and sort by icir descending, then id ascending for ties
    paired = list(zip(evaluations, factor_specs))
    paired.sort(key=lambda x: (-x[0].icir, x[1].id))

    # Limit to top_k candidates
    candidate_pool = paired[:top_k]

    # Greedy deduplication
    selected: list[tuple[FactorEvaluation, FactorSpec]] = []
    removed_ids: list[str] = []

    for ev, spec in candidate_pool:
        is_redundant = False
        for sel_ev, _sel_spec in selected:
            corr = _pearson_ic_correlation(ev, sel_ev)
            if abs(corr) >= corr_threshold:
                is_redundant = True
                removed_ids.append(spec.id)
                break
        if not is_redundant:
            selected.append((ev, spec))

    # Extract spec list
    selected_specs = [spec for _ev, spec in selected]

    # Log if candidate count is fewer than top_k (AC-FR0400-03)
    final_k = len(selected_specs)
    if len(evaluations) < top_k:
        logger.warning(
            "selected fewer than top_k because candidate count < top_k; "
            "final=%d, requested=%d, candidates=%d",
            final_k,
            top_k,
            len(evaluations),
        )

    return selected_specs, SelectionDiagnostics(
        removed_by_redundancy=removed_ids,
        final_k=final_k,
        top_k_requested=top_k,
    )


def _pearson_ic_correlation(a: FactorEvaluation, b: FactorEvaluation) -> float:
    """Compute Pearson correlation between two factors' daily IC time series.

    Joins the IC DataFrames on ``date`` and computes the Pearson correlation
    coefficient of the aligned ``ic`` columns.

    Returns:
        Pearson correlation coefficient in [-1, 1]. Returns 0.0 when
        there are fewer than 3 overlapping dates (undefined correlation).
    """
    # Join on date
    joined = a.ic_ts.join(b.ic_ts, on="date", how="inner", suffix="_b")

    if len(joined) < 3:
        return 0.0

    ic_a = joined["ic"].to_numpy()
    ic_b = joined["ic_b"].to_numpy()

    # Handle constant series (std ≈ 0)
    std_a = np.std(ic_a)
    std_b = np.std(ic_b)
    if std_a < 1e-12 or std_b < 1e-12:
        return 0.0

    return float(np.corrcoef(ic_a, ic_b)[0, 1])
