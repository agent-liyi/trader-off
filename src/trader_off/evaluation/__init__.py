"""Prediction evaluation: IC, Rank IC, layered returns."""

from trader_off.evaluation.ic import compute_layered_returns, ic_pearson, ic_spearman
from trader_off.evaluation.report import PredictionQualityReport, evaluate_predictions

__all__ = [
    "ic_pearson",
    "ic_spearman",
    "compute_layered_returns",
    "evaluate_predictions",
    "PredictionQualityReport",
]
