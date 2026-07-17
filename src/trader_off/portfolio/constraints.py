"""Optimization constraints as data specs (FR-3300~3600).

This module provides factory functions that return constraint data
consumable by scipy.optimize and cvxpy solvers in FR-3700.
Constraints are pure data — no solving is performed here.

  - full_position_constraint(n)  → (a_eq, b_eq) for Σw = 1
  - long_only_constraint(n)      → (lb, ub) for w_i ≥ 0
"""

import numpy as np


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
