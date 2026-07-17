"""Factor scoring — compute factor values from FactorSpec (FR-0900).

Bridges factor mining output to v0.1.0 training input by applying
FactorSpec compute_fn callables to raw OHLCV data. The resulting
DataFrame columns are named by each spec's ``id``, producing the
feature matrix that replaces v0.1.0's default 15 features.
"""

from __future__ import annotations

import polars as pl

from trader_off.factor_mining.expression import FactorSpec


def compute_factor_score(
    specs: list[FactorSpec],
    raw_data: pl.DataFrame,
) -> pl.DataFrame:
    """Compute factor values for each FactorSpec from raw market data.

    Each spec's ``compute_fn`` is applied to ``raw_data`` (pre-sorted by
    ``asset`` and ``date``), producing a pl.Series of factor values.
    Results are concatenated into a DataFrame with columns named by each
    spec's ``id``.

    The output DataFrame has the same number of rows as ``raw_data``,
    preserving row ordering for alignment with training labels.  All
    columns are Float64 dtype, consistent with v0.1.0's expected feature
    format.

    Args:
        specs: FactorSpec instances, each with a ``compute_fn`` callable
            that accepts a ``pl.DataFrame`` and returns a ``pl.Series``.
        raw_data: Input market data (OHLCV DataFrame). Must contain
            columns expected by each spec's ``compute_fn`` (typically
            ``asset``, ``date``, ``open``, ``high``, ``low``, ``close``,
            ``volume``, etc.).

    Returns:
        DataFrame with columns named after each spec's ``id``. Column
        dtypes are Float64. Row count equals ``raw_data`` row count.

    Raises:
        ValueError: If ``specs`` is empty or contains duplicate ``id``
            values.
    """
    if not specs:
        raise ValueError("specs must not be empty")

    # Guard against duplicate spec IDs (ambiguous column names)
    seen: set[str] = set()
    for spec in specs:
        if spec.id in seen:
            raise ValueError(f"duplicate spec id: {spec.id!r}")
        seen.add(spec.id)

    # Pre-sort for consistent row ordering across all factors.
    # Each compute_fn also sorts internally, making it a no-op.
    data = raw_data.sort(["asset", "date"])

    columns: dict[str, pl.Series] = {}
    for spec in specs:
        factor_values = spec.compute_fn(data)
        columns[spec.id] = factor_values

    return pl.DataFrame(columns)
