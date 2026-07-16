"""Prediction quality evaluation report (FR-1300).

Aggregates daily IC, Rank IC, and layered returns into a
PredictionQualityReport dataclass.
"""

from dataclasses import dataclass

import polars as pl

from trader_off.evaluation.ic import (
    compute_layered_returns,
    ic_pearson,
    ic_spearman,
)


@dataclass
class PredictionQualityReport:
    """Container for prediction quality evaluation results.

    Attributes:
        ic_ts: Daily Pearson IC time series (date, ic).
        rank_ic_ts: Daily Spearman Rank IC time series (date, rank_ic).
        ic_mean: Mean daily IC.
        ic_std: Standard deviation of daily IC.
        rank_ic_mean: Mean daily Rank IC.
        rank_ic_std: Standard deviation of daily Rank IC.
        layered_returns: Mean return by prediction layer (layer, mean_return).
    """

    ic_ts: pl.DataFrame
    rank_ic_ts: pl.DataFrame
    ic_mean: float
    ic_std: float
    rank_ic_mean: float
    rank_ic_std: float
    layered_returns: pl.DataFrame


def evaluate_predictions(
    predictions: pl.DataFrame,
    labels: pl.DataFrame,
    n_layers: int = 5,
) -> PredictionQualityReport:
    """Compute prediction quality metrics from aligned predictions and labels.

    Args:
        predictions: DataFrame with columns date, asset, score.
        labels: DataFrame with columns date, asset, label.
        n_layers: Number of return layers (default 5).

    Returns:
        PredictionQualityReport with IC time series and layered returns.
    """
    # Merge predictions and labels
    merged = predictions.join(labels, on=["date", "asset"], how="inner")

    if len(merged) == 0:
        return PredictionQualityReport(
            ic_ts=pl.DataFrame(schema={"date": pl.Date, "ic": pl.Float64}),
            rank_ic_ts=pl.DataFrame(schema={"date": pl.Date, "rank_ic": pl.Float64}),
            ic_mean=0.0,
            ic_std=0.0,
            rank_ic_mean=0.0,
            rank_ic_std=0.0,
            layered_returns=compute_layered_returns(predictions, labels, n_layers),
        )

    # Compute daily IC
    dates = merged["date"].unique().sort()
    ic_rows: list[dict] = []
    rank_ic_rows: list[dict] = []

    for d in dates.to_list():
        day_data = merged.filter(pl.col("date") == d)
        ic_val = ic_pearson(day_data["score"], day_data["label"])
        rank_ic_val = ic_spearman(day_data["score"], day_data["label"])
        ic_rows.append({"date": d, "ic": ic_val})
        rank_ic_rows.append({"date": d, "rank_ic": rank_ic_val})

    ic_ts = pl.DataFrame(ic_rows, schema={"date": pl.Date, "ic": pl.Float64})
    rank_ic_ts = pl.DataFrame(rank_ic_rows, schema={"date": pl.Date, "rank_ic": pl.Float64})

    ic_vals = ic_ts["ic"].to_numpy()
    rank_ic_vals = rank_ic_ts["rank_ic"].to_numpy()

    return PredictionQualityReport(
        ic_ts=ic_ts,
        rank_ic_ts=rank_ic_ts,
        ic_mean=float(ic_vals.mean()) if len(ic_vals) > 0 else 0.0,
        ic_std=float(ic_vals.std()) if len(ic_vals) > 0 else 0.0,
        rank_ic_mean=float(rank_ic_vals.mean()) if len(rank_ic_vals) > 0 else 0.0,
        rank_ic_std=float(rank_ic_vals.std()) if len(rank_ic_vals) > 0 else 0.0,
        layered_returns=compute_layered_returns(predictions, labels, n_layers),
    )
