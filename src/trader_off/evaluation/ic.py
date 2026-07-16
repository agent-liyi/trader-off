"""Information Coefficient (IC) computation (FR-1300).

Pure functions for Pearson IC, Spearman Rank IC, and layered returns.
"""

import numpy as np
import polars as pl
from scipy import stats as scipy_stats


def ic_pearson(pred: pl.Series, label: pl.Series) -> float:
    """Compute Pearson correlation between predictions and labels.

    Args:
        pred: Predicted scores.
        label: True labels.

    Returns:
        Pearson correlation coefficient in [-1, 1].
    """
    pred_np = pred.to_numpy()
    label_np = label.to_numpy()
    mask = ~np.isnan(pred_np) & ~np.isnan(label_np)
    if mask.sum() < 3:
        return 0.0
    r, _ = scipy_stats.pearsonr(pred_np[mask], label_np[mask])
    return float(r)


def ic_spearman(pred: pl.Series, label: pl.Series) -> float:
    """Compute Spearman rank correlation between predictions and labels.

    Args:
        pred: Predicted scores.
        label: True labels.

    Returns:
        Spearman rank correlation coefficient in [-1, 1].
    """
    pred_np = pred.to_numpy()
    label_np = label.to_numpy()
    mask = ~np.isnan(pred_np) & ~np.isnan(label_np)
    if mask.sum() < 3:
        return 0.0
    r, _ = scipy_stats.spearmanr(pred_np[mask], label_np[mask])
    return float(r)


def compute_layered_returns(
    predictions: pl.DataFrame,
    labels: pl.DataFrame,
    n_layers: int = 5,
) -> pl.DataFrame:
    """Compute mean returns by prediction quintile layers.

    Assets are sorted by score and divided into n_layers equally-sized
    groups. The mean label (return) per layer is returned.

    Args:
        predictions: DataFrame with columns date, asset, score.
        labels: DataFrame with columns date, asset, label.
        n_layers: Number of layers (default 5).

    Returns:
        DataFrame with columns layer (Int32) and mean_return (Float64).
    """
    # Merge predictions with labels on (date, asset)
    merged = predictions.join(labels, on=["date", "asset"], how="inner")

    if len(merged) == 0:
        return pl.DataFrame(
            {"layer": list(range(1, n_layers + 1)), "mean_return": [0.0] * n_layers},
            schema={"layer": pl.Int32, "mean_return": pl.Float64},
        )

    # Sort by score descending and assign layer
    merged = merged.sort("score", descending=True)
    n = len(merged)
    layer_size = max(1, n // n_layers)

    layer_returns: list[float] = []
    for i in range(n_layers):
        start = i * layer_size
        end = start + layer_size if i < n_layers - 1 else n
        chunk = merged[start:end]
        mean_ret = chunk["label"].mean()
        layer_returns.append(mean_ret if mean_ret is not None else 0.0)

    return pl.DataFrame({
        "layer": list(range(1, n_layers + 1)),
        "mean_return": layer_returns,
    }, schema={"layer": pl.Int32, "mean_return": pl.Float64})
