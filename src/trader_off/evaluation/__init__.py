"""Prediction evaluation: IC, Rank IC, layered returns."""

from trader_off.evaluation.ic import ic_pearson, ic_spearman, compute_layered_returns
from trader_off.evaluation.report import evaluate_predictions, PredictionQualityReport

__all__ = [
    "ic_pearson",
    "ic_spearman",
    "compute_layered_returns",
    "evaluate_predictions",
    "PredictionQualityReport",
]
