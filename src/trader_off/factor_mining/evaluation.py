"""Factor evaluation — IC / ICIR / Rank IC (FR-0300).

Reuses v0.1.0 ``trader_off.evaluation.ic`` for IC computation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl

from trader_off.evaluation.ic import (
    compute_layered_returns,
    ic_pearson,
    ic_spearman,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FactorEvaluation:
    """Container for factor evaluation results.

    Attributes:
        ic_ts: Daily Pearson IC time series (date, ic).
        rank_ic_ts: Daily Spearman Rank IC time series (date, rank_ic).
        ic_mean: Mean daily Pearson IC.
        ic_std: Standard deviation of daily Pearson IC.
        icir: Information Coefficient IR = ic_mean / ic_std.
        rank_ic_mean: Mean daily Rank IC.
        rank_ic_std: Standard deviation of daily Rank IC.
        layered_returns: Mean return by prediction layer (layer, mean_return, 5 rows).
    """

    ic_ts: pl.DataFrame
    rank_ic_ts: pl.DataFrame
    ic_mean: float
    ic_std: float
    icir: float
    rank_ic_mean: float
    rank_ic_std: float
    layered_returns: pl.DataFrame


def evaluate_factor(
    factor_values: pl.DataFrame,
    labels: pl.DataFrame,
    dates: list[date],
) -> FactorEvaluation:
    """Evaluate a factor via IC, Rank IC, ICIR, and layered returns.

    Computes daily Pearson IC and Spearman Rank IC by joining
    factor values and labels on (asset, date), then aggregates
    summary statistics across all evaluated dates.

    Internally delegates to v0.1.0 ``trader_off.evaluation.ic``
    functions for IC and layered returns computation.

    Args:
        factor_values: DataFrame with columns ``asset``, ``date``, ``value``.
        labels: DataFrame with columns ``asset``, ``date``, ``label``.
        dates: Trading dates to evaluate. Dates not present in the data
            are skipped silently.

    Returns:
        FactorEvaluation with IC time series, summary statistics,
        and 5-layer return analysis.

    Raises:
        ValueError: If required columns are missing from input DataFrames.
    """
    # Validate required columns
    _validate_columns(factor_values, {"asset", "date", "value"}, "factor_values")
    _validate_columns(labels, {"asset", "date", "label"}, "labels")

    # Merge factor values and labels on (asset, date)
    merged = factor_values.join(labels, on=["asset", "date"], how="inner")

    if len(merged) == 0:
        return _empty_result(factor_values, labels)

    # Compute daily IC per date
    ic_rows, rank_ic_rows = _compute_daily_ic(merged, dates)

    # Build time-series DataFrames
    ic_ts = pl.DataFrame(
        ic_rows,
        schema={"date": pl.Date, "ic": pl.Float64},
    ).sort("date")
    rank_ic_ts = pl.DataFrame(
        rank_ic_rows,
        schema={"date": pl.Date, "rank_ic": pl.Float64},
    ).sort("date")

    # Compute summary statistics — handle NaN (e.g., constant factor → undefined correlation)
    ic_vals = ic_ts["ic"].to_numpy()
    rank_ic_vals = rank_ic_ts["rank_ic"].to_numpy()

    ic_mean = float(np.nan_to_num(np.nanmean(ic_vals), nan=0.0)) if len(ic_vals) > 0 else 0.0
    ic_std = float(np.nan_to_num(np.nanstd(ic_vals, ddof=0), nan=0.0)) if len(ic_vals) > 0 else 0.0
    rank_ic_mean = (
        float(np.nan_to_num(np.nanmean(rank_ic_vals), nan=0.0)) if len(rank_ic_vals) > 0 else 0.0
    )
    rank_ic_std = (
        float(np.nan_to_num(np.nanstd(rank_ic_vals, ddof=0), nan=0.0))
        if len(rank_ic_vals) > 0
        else 0.0
    )

    # ICIR = ic_mean / ic_std; handle zero std
    if ic_std == 0.0:
        icir = 0.0
        logger.warning("factor has zero std, icir set to 0")
    else:
        icir = ic_mean / ic_std

    # Compute layered returns — rename value → score for v0.1.0 API
    predictions_for_layered = factor_values.rename({"value": "score"})
    layered_returns = compute_layered_returns(predictions_for_layered, labels)

    return FactorEvaluation(
        ic_ts=ic_ts,
        rank_ic_ts=rank_ic_ts,
        ic_mean=ic_mean,
        ic_std=ic_std,
        icir=icir,
        rank_ic_mean=rank_ic_mean,
        rank_ic_std=rank_ic_std,
        layered_returns=layered_returns,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_columns(df: pl.DataFrame, required: set[str], name: str) -> None:
    """Raise ValueError if ``df`` is missing any ``required`` column."""
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{name} is missing required columns: {sorted(missing)}")


def _compute_daily_ic(
    merged: pl.DataFrame,
    dates: list[date],
) -> tuple[list[dict], list[dict]]:
    """Compute daily IC and Rank IC for each date in ``dates``.

    Returns two lists of dicts suitable for constructing ic_ts / rank_ic_ts.
    """
    ic_rows: list[dict] = []
    rank_ic_rows: list[dict] = []

    for d in dates:
        day_data = merged.filter(pl.col("date") == d)
        if len(day_data) == 0:
            continue

        ic_val = ic_pearson(day_data["value"], day_data["label"])
        rank_ic_val = ic_spearman(day_data["value"], day_data["label"])

        ic_rows.append({"date": d, "ic": ic_val})
        rank_ic_rows.append({"date": d, "rank_ic": rank_ic_val})

    return ic_rows, rank_ic_rows


def _empty_result(
    factor_values: pl.DataFrame,
    labels: pl.DataFrame,
) -> FactorEvaluation:
    """Return a FactorEvaluation with zero/empty fields for empty input."""
    return FactorEvaluation(
        ic_ts=pl.DataFrame(schema={"date": pl.Date, "ic": pl.Float64}),
        rank_ic_ts=pl.DataFrame(schema={"date": pl.Date, "rank_ic": pl.Float64}),
        ic_mean=0.0,
        ic_std=0.0,
        icir=0.0,
        rank_ic_mean=0.0,
        rank_ic_std=0.0,
        layered_returns=compute_layered_returns(factor_values.rename({"value": "score"}), labels),
    )
