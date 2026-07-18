"""Optimization constraints as data specs (FR-3300~3600).

This module provides factory functions that return constraint data
consumable by scipy.optimize and cvxpy solvers in FR-3700.
Constraints are pure data — no solving is performed here.

  - full_position_constraint(n)  → (a_eq, b_eq) for Σw = 1
  - long_only_constraint(n)      → (lb, ub) for w_i ≥ 0
  - industry_neutral_constraint(...) → (a_eq, b_eq) for Σ(w_i - b_i) = 0 per industry
  - max_position_constraint(...) → (lb, ub) for w_i ≤ max_weight
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OptimizerConstraints:
    """Constraint bundle for the Max Sharpe portfolio optimizer.

    Attributes:
        sum_to_one: Enforce Σw = 1 (full investment).
        long_only: Enforce w_i ≥ 0 for all assets.
        max_weight: Per-asset upper bound on weight (e.g. 0.10 for 10%).
        industry_neutral: Enforce industry active weights are bounded by tol.
        industry_neutral_tol: Maximum allowed absolute deviation from the
            industry benchmark weight (default 0.05).
        industry_benchmark: Mapping from industry name to benchmark weight.
            ``None`` means equal-weight benchmark per industry.
    """

    sum_to_one: bool = True
    long_only: bool = True
    max_weight: float = 0.10
    industry_neutral: bool = True
    industry_neutral_tol: float = 0.05
    industry_benchmark: dict[str, float] | None = None


def full_position_constraint(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Generate the full-position equality constraint (Σw = 1).

    Returns a_eq (shape ``(1, n)``, all ones) and b_eq ``[1.0]``,
    representing the linear constraint ``a_eq @ w == b_eq``.

    Args:
        n: Number of assets (portfolio dimension).

    Returns:
        Tuple of ``(A_eq, b_eq)`` arrays suitable for scipy's
        ``constraints`` or cvxpy's ``cp.sum(w) == 1``.
    """
    a_eq = np.ones((1, n), dtype=np.float64)
    b_eq = np.array([1.0], dtype=np.float64)
    return a_eq, b_eq


def long_only_constraint(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Generate long-only bounds (w_i ≥ 0 for all assets).

    Returns ``lb`` (zeros) and ``ub`` (inf) arrays, each of length *n*.

    Args:
        n: Number of assets.

    Returns:
        Tuple of ``(lb, ub)`` where ``lb`` is all zeros and ``ub`` is
        all ``inf``, suitable as scipy ``bounds`` or cvxpy ``w >= 0``.
    """
    lb = np.zeros(n, dtype=np.float64)
    ub = np.full(n, np.inf, dtype=np.float64)
    return lb, ub


def industry_neutral_constraint(
    tickers: list[str],
    industry_map: dict[str, str],
    benchmark_weights: dict[str, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Generate per-industry active-weight equality constraint.

    For each industry ``j`` the returned matrices enforce
    ``Σ_{i ∈ j} (w_i - benchmark_i) = 0``, i.e.
    ``Σ_{i ∈ j} w_i = Σ_{i ∈ j} benchmark_i``.

    Args:
        tickers: Ordered list of asset tickers (length N).
        industry_map: Mapping from ticker to industry name.
        benchmark_weights: Mapping from ticker to benchmark weight.

    Returns:
        ``(A_eq, b_eq)`` where ``A_eq`` has one row per industry and
        ``b_eq[j]`` equals the total benchmark weight of industry ``j``.

    Raises:
        ValueError: If a ticker is missing from ``industry_map`` or
            ``benchmark_weights``.
    """
    missing_tickers = [t for t in tickers if t not in industry_map]
    if missing_tickers:
        raise ValueError(f"tickers missing from industry_map: {missing_tickers}")

    missing_tickers = [t for t in tickers if t not in benchmark_weights]
    if missing_tickers:
        raise ValueError(f"tickers missing from benchmark_weights: {missing_tickers}")

    industries = sorted({industry_map[t] for t in tickers})
    n = len(tickers)
    m = len(industries)
    a_eq = np.zeros((m, n), dtype=np.float64)
    b_eq = np.zeros(m, dtype=np.float64)
    industry_array = np.array([industry_map[t] for t in tickers])

    for row_idx, industry in enumerate(industries):
        mask = industry_array == industry
        a_eq[row_idx, mask] = 1.0
        b_eq[row_idx] = sum(
            benchmark_weights[ticker] for ticker, is_member in zip(tickers, mask) if is_member
        )

    return a_eq, b_eq
