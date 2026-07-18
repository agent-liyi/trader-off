"""Equal-weight baseline comparison (FR-3900).

Provides:
  - equal_weight_portfolio(tickers) -> np.ndarray: uniform 1/N weights
  - compare_to_baseline(weights, mu, cov, w_prev=None) -> ComparisonReport:
      compares optimized portfolio vs equal-weight baseline on:
      expected_return, volatility, Sharpe, max_weight, turnover
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from loguru import logger


@dataclass(frozen=True)
class ComparisonReport:
    """Result of comparing an optimized portfolio against the equal-weight baseline.

    Attributes:
        optimized: Dict of metrics for the optimized portfolio.
        equal_weight: Dict of metrics for the equal-weight baseline.
        delta: Difference (optimized - equal_weight) for each metric.
    """

    optimized: dict[str, float]
    equal_weight: dict[str, float]
    delta: dict[str, float]


def equal_weight_portfolio(tickers: list[str]) -> np.ndarray:
    """Build a uniform 1/N weight vector.

    Args:
        tickers: List of asset identifiers.

    Returns:
        np.ndarray of shape (N,) with equal weights summing to 1.0.
    """
    n = len(tickers)
    if n == 0:
        return np.array([], dtype=np.float64)
    return np.full(n, 1.0 / n, dtype=np.float64)


def _portfolio_metrics(
    weights: np.ndarray,
    mu: dict[str, float],
    cov: np.ndarray,
    tickers: list[str],
) -> dict[str, float]:
    """Compute expected_return, volatility, Sharpe, max_weight for a weight vector.

    Args:
        weights: Asset weights (length N).
        mu: Expected returns per asset.
        cov: (N, N) covariance matrix.
        tickers: Ordered list of asset identifiers.

    Returns:
        Dict with expected_return, volatility, sharpe, max_weight.
    """
    mu_vec = np.array([mu[t] for t in tickers], dtype=np.float64)
    expected_return = float(np.dot(mu_vec, weights))
    volatility = float(np.sqrt(np.dot(weights, np.dot(cov, weights))))
    sharpe = expected_return / volatility if volatility > 0 else 0.0
    max_weight = float(weights.max())
    return {
        "expected_return": expected_return,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_weight": max_weight,
    }


def _turnover(weights: np.ndarray, w_prev: np.ndarray | None) -> float:
    """Compute portfolio turnover.

    Turnover = 0.5 * sum(|w - w_prev|).

    Args:
        weights: Current weights.
        w_prev: Previous weights (None means first run, use zero vector).

    Returns:
        Turnover as a float.
    """
    prev = np.zeros_like(weights) if w_prev is None else w_prev
    return float(0.5 * np.sum(np.abs(weights - prev)))


def compare_to_baseline(
    weights: np.ndarray,
    mu: dict[str, float],
    cov: np.ndarray,
    w_prev: np.ndarray | None = None,
) -> ComparisonReport:
    """Compare optimized portfolio against equal-weight baseline.

    Args:
        weights: Optimized asset weights (length N).
        mu: Expected returns per asset.
        cov: (N, N) covariance matrix.
        w_prev: Previous portfolio weights for turnover calculation.
            If None, assumed to be all zeros (first run, turnover = 0.5).

    Returns:
        ComparisonReport with optimized, equal_weight, and delta dicts.
    """
    tickers = list(mu.keys())
    n = len(tickers)

    # Equal-weight baseline
    w_eq = equal_weight_portfolio(tickers)

    # Metrics for optimized portfolio
    opt_metrics = _portfolio_metrics(weights, mu, cov, tickers)
    opt_metrics["turnover"] = _turnover(weights, w_prev)

    # Metrics for equal-weight baseline
    eq_metrics = _portfolio_metrics(w_eq, mu, cov, tickers)
    eq_metrics["turnover"] = _turnover(w_eq, w_prev)

    # Delta (optimized - equal_weight)
    delta = {k: opt_metrics[k] - eq_metrics[k] for k in opt_metrics}

    # Warning if optimized Sharpe is lower than baseline
    if opt_metrics["sharpe"] < eq_metrics["sharpe"]:
        logger.warning(
            f"optimized sharpe ({opt_metrics['sharpe']:.4f}) < baseline ({eq_metrics['sharpe']:.4f}), "
            "check inputs"
        )

    return ComparisonReport(
        optimized=opt_metrics,
        equal_weight=eq_metrics,
        delta=delta,
    )
