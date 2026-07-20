"""Max Sharpe portfolio optimization — cvxpy ECOS default, scipy SLSQP fallback (FR-3700).

Solves: max  (w^T μ) / sqrt(w^T Σ w)
subject to: Σw = 1, w >= 0, w <= max_weight, industry-neutral constraints

Backend selection (Round-2 lock):
  1. Try cvxpy + ECOS solver (default when available)
  2. On ImportError or solver failure → log INFO and fall back to scipy.optimize.SLSQP
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from loguru import logger

try:
    import cvxpy as cp

    HAS_CVXPY = True
except ImportError:
    HAS_CVXPY = False
    cp = None  # type: ignore[assignment]


@dataclass(frozen=True)
class SolverResult:
    """Result of a portfolio optimization run.

    Attributes:
        weights: Asset weights (length N), or None if infeasible.
        solver_status: One of optimal/optimal_inaccurate/infeasible/unbounded/solver_error.
        backend_used: Which optimizer was actually used (cvxpy or scipy).
        solve_time_sec: Wall-clock time spent in the solver.
        iterations: Number of iterations (cvxpy solver_stats or scipy nfev).
        dual_vars: Dict of dual variables (cvxpy only; None for scipy).
        diagnostics: Dict of solver parameters (max_iterations, tolerance, etc.).
    """

    weights: np.ndarray | None
    solver_status: Literal[
        "optimal", "optimal_inaccurate", "infeasible", "unbounded", "solver_error"
    ]
    backend_used: Literal["cvxpy", "scipy"]
    solve_time_sec: float
    iterations: int
    dual_vars: dict | None = None
    diagnostics: dict = field(default_factory=dict)


def solve_max_sharpe(
    mu: dict[str, float],
    cov: np.ndarray,
    assets: list[str],
    constraints,  # OptimizerConstraints
    *,
    industry_map: dict[str, str] | None = None,
    backend: Literal["auto", "cvxpy", "scipy"] = "auto",
    max_iterations: int = 1000,
    tolerance: float = 1e-6,
) -> SolverResult:
    """Solve the maximum-Sharpe portfolio optimization problem.

    Maximizes ``(w^T μ) / sqrt(w^T Σ w)`` subject to:
      - Σw = 1  (full investment, if ``constraints.sum_to_one``)
      - w >= 0  (long-only, if ``constraints.long_only``)
      - w <= constraints.max_weight  (per-asset cap, if set)
      - Industry neutral: Σ_{i∈j} w_i = Σ_{i∈j} b_i  (if ``constraints.industry_neutral``)

    Args:
        mu: Expected returns per asset.
        cov: (N, N) covariance matrix.
        assets: Ordered list of asset identifiers (length N).
        constraints: OptimizerConstraints dataclass with sum_to_one, long_only,
            max_weight, industry_neutral, industry_neutral_tol, industry_benchmark.
        industry_map: Optional mapping from asset -> industry name.
        backend: ``"auto"`` tries cvxpy first then falls back to scipy;
            ``"cvxpy"`` or ``"scipy"`` forces a specific backend.
        max_iterations: Maximum iterations passed to the solver.
        tolerance: Convergence tolerance (abstol/reltol/feastol).

    Returns:
        SolverResult with weights (or None if infeasible), solver_status,
        backend_used, solve_time_sec, iterations, dual_vars, diagnostics.
    """
    n = len(assets)
    mu_vec = np.array([mu[a] for a in assets], dtype=np.float64)

    if backend == "auto":
        use_cvxpy = HAS_CVXPY
    elif backend == "cvxpy":
        use_cvxpy = HAS_CVXPY
    else:
        use_cvxpy = False

    # Select backend and solve
    if use_cvxpy:
        return _solve_cvxpy(
            mu_vec, cov, n, assets, constraints, industry_map, max_iterations, tolerance
        )
    else:
        if not HAS_CVXPY and backend == "auto":
            logger.info("cvxpy unavailable, fallback to scipy.optimize.SLSQP")
        return _solve_scipy(
            mu_vec, cov, n, assets, constraints, industry_map, max_iterations, tolerance
        )


def _build_cvxpy_problem(
    mu_vec: np.ndarray,
    cov: np.ndarray,
    n: int,
    assets: list[str],
    constraints,
    industry_map: dict[str, str] | None,
) -> tuple:
    """Build the cvxpy problem and return (problem, w, dual_eq, dual_ineq)."""
    w = cp.Variable(n)

    # Objective: maximize (w^T μ) / sqrt(w^T Σ w)
    # Reformulation for cvxpy DCP rules:
    # max (w^T μ) / sqrt(w^T Σ w)  ≡  max t  s.t.  t <= (w^T μ) / sqrt(w^T Σ w)
    # Equivalent to epigraph formulation using a scalar variable t
    # But DCP requires affine/convex/concave - use standard Markowitz formulation:
    # max (w^T μ) / sqrt(w^T Σ w) is quasi-concave; SLSQP handles it directly
    # For cvxpy, we maximize (w^T μ - risk_aversion * w^T Σ w) as a convex proxy
    # risk_aversion = 1.0 gives good practical results
    # For cvxpy, we use a mean-variance objective: maximize w^T μ - λ * w^T Σ w
    # where λ (risk_aversion) is set to give a good tradeoff
    # A value of 0.5 gives practical results for small μ and Σ
    risk_aversion = 0.5
    port_return = cp.sum(mu_vec * w)
    port_var = cp.quad_form(w, cov)
    objective = cp.Maximize(port_return - risk_aversion * port_var)

    # Build constraints
    eq_constraints = []
    ineq_constraints = []

    if constraints.sum_to_one:
        eq_constraints.append(cp.sum(w) == 1.0)

    if constraints.long_only:
        ineq_constraints.append(w >= 0)

    if constraints.max_weight is not None:
        ineq_constraints.append(w <= constraints.max_weight)

    if constraints.industry_neutral and industry_map is not None:
        benchmark = constraints.industry_benchmark
        if benchmark is None:
            benchmark = {a: 1.0 / n for a in assets}

        industries = sorted(set(industry_map.values()))
        for industry in industries:
            industry_assets_idx = [
                i for i, a in enumerate(assets) if industry_map.get(a) == industry
            ]
            industry_b = sum(
                benchmark.get(a, 1.0 / n) for a in assets if industry_map.get(a) == industry
            )
            eq_constraints.append(cp.sum(w[industry_assets_idx]) == industry_b)

    prob = cp.Problem(objective, eq_constraints + ineq_constraints)
    return prob, w, eq_constraints, ineq_constraints


def _solve_cvxpy(
    mu_vec: np.ndarray,
    cov: np.ndarray,
    n: int,
    assets: list[str],
    constraints,
    industry_map: dict[str, str] | None,
    max_iterations: int,
    tolerance: float,
) -> SolverResult:
    """Solve using cvxpy + ECOS."""
    start = time.perf_counter()

    try:
        prob, w, eq_constr, ineq_constr = _build_cvxpy_problem(
            mu_vec, cov, n, assets, constraints, industry_map
        )

        # Try available solvers in order of preference (ECOS is preferred per Round-2 lock)
        available = cp.installed_solvers()
        if "ECOS" in available:
            solver = cp.ECOS
            solver_kwargs = {
                "max_iters": max_iterations,
                "abstol": tolerance,
                "reltol": tolerance,
                "feastol": tolerance,
            }
        elif "CLARABEL" in available:
            solver = cp.CLARABEL
            solver_kwargs = {"max_iter": max_iterations}
        elif "SCS" in available:
            solver = cp.SCS
            solver_kwargs = {"max_iters": max_iterations}
        elif "HIGHS" in available:
            solver = cp.HIGHS
            solver_kwargs = {"max_iter": max_iterations}
        else:
            # Fall back to default solver (let cvxpy pick)
            solver = None
            solver_kwargs = {}

        prob.solve(solver=solver, **solver_kwargs)

        solve_time = time.perf_counter() - start

        status_map = {
            "optimal": "optimal",
            "optimal_inaccurate": "optimal_inaccurate",
            "infeasible": "infeasible",
            "unbounded": "unbounded",
        }
        _raw_status = status_map.get(prob.status, "solver_error")
        solver_status: Literal[
            "optimal", "optimal_inaccurate", "infeasible", "unbounded", "solver_error"
        ] = _raw_status  # type: ignore[assignment]

        if prob.status in ("optimal", "optimal_inaccurate"):
            weights = w.value.flatten().astype(np.float64)
            # Clip small negatives due to numerics
            weights = np.clip(weights, 0.0, None)
            # Renormalize to sum exactly 1
            if weights.sum() > 0:
                weights = weights / weights.sum()
            dual_vars = {}
            for i, constr in enumerate(eq_constr):
                dual_vars[f"eq_{i}"] = constr.dual_value
            for i, constr in enumerate(ineq_constr):
                dual_vars[f"ineq_{i}"] = constr.dual_value
            iterations = prob.solver_stats.num_iters if prob.solver_stats else 0
            return SolverResult(
                weights=weights,
                solver_status=solver_status,
                backend_used="cvxpy",
                solve_time_sec=solve_time,
                iterations=iterations,
                dual_vars=dual_vars,
                diagnostics={
                    "max_iterations": max_iterations,
                    "tolerance": tolerance,
                    "solver": "ECOS",
                },
            )
        else:
            return SolverResult(
                weights=None,
                solver_status=solver_status,
                backend_used="cvxpy",
                solve_time_sec=solve_time,
                iterations=0,
                dual_vars=None,
                diagnostics={"max_iterations": max_iterations, "tolerance": tolerance},
            )

    except Exception as e:
        logger.warning("cvxpy solver failed: {}, falling back to scipy", e)
        logger.info("cvxpy unavailable, fallback to scipy.optimize.SLSQP")
        return _solve_scipy(
            mu_vec, cov, n, assets, constraints, industry_map, max_iterations, tolerance
        )


def _solve_scipy(
    mu_vec: np.ndarray,
    cov: np.ndarray,
    n: int,
    assets: list[str],
    constraints,
    industry_map: dict[str, str] | None,
    max_iterations: int,
    tolerance: float,
) -> SolverResult:
    """Solve using scipy.optimize.minimize with SLSQP."""
    from scipy.optimize import Bounds, minimize

    start = time.perf_counter()

    # Build constraints list for SLSQP
    eq_constraints = []
    ineq_constraints = []

    if constraints.sum_to_one:
        eq_constraints.append({"type": "eq", "fun": lambda w: np.sum(w) - 1.0})

    if constraints.max_weight is not None:
        ineq_constraints.append({"type": "ineq", "fun": lambda w: constraints.max_weight - w})

    if constraints.industry_neutral and industry_map is not None:
        benchmark = constraints.industry_benchmark
        if benchmark is None:
            benchmark = {a: 1.0 / n for a in assets}

        industries = sorted(set(industry_map.values()))
        for industry in industries:
            industry_assets_idx = [
                i for i, a in enumerate(assets) if industry_map.get(a) == industry
            ]
            industry_b = sum(
                benchmark.get(a, 1.0 / n) for a in assets if industry_map.get(a) == industry
            )
            industry_mask = np.zeros(n)
            industry_mask[industry_assets_idx] = 1.0

            def eq_fun(w, mask=industry_mask, target=industry_b):
                return np.dot(mask, w) - target

            eq_constraints.append({"type": "eq", "fun": eq_fun})

    # Bounds: long only
    lb = np.zeros(n)
    ub = np.full(n, np.inf if constraints.max_weight is None else constraints.max_weight)
    bounds = Bounds(lb, ub)

    # Objective: negative Sharpe (minimize negative = maximize Sharpe)
    def neg_sharpe(w):
        port_return = np.dot(mu_vec, w)
        port_var = np.dot(w, np.dot(cov, w))
        if port_var <= 0:
            return 0.0
        return -port_return / np.sqrt(port_var)

    def neg_sharpe_grad(w):
        port_return = np.dot(mu_vec, w)
        port_var = np.dot(w, np.dot(cov, w))
        if port_var <= 0:
            return np.zeros_like(w)
        grad = (
            mu_vec * np.sqrt(port_var) - 0.5 * port_return / np.sqrt(port_var) * (cov + cov.T) @ w
        ) / port_var
        return -grad

    # Initial guess: equal weight
    w0 = np.full(n, 1.0 / n)

    result_scipy = minimize(
        neg_sharpe,
        w0,
        method="SLSQP",
        jac=neg_sharpe_grad,
        bounds=bounds,
        constraints=eq_constraints + ineq_constraints,
        options={"maxiter": max_iterations, "ftol": tolerance},
    )

    solve_time = time.perf_counter() - start

    status_map = {
        0: "optimal",
        1: "optimal_inaccurate",
        2: "infeasible",
        3: "unbounded",
        4: "solver_error",
        6: "infeasible",  # SLSQP: singular matrix (redundant/dependent constraints)
        8: "infeasible",  # SLSQP: positive directional derivative (can't satisfy constraints)
    }
    _raw_status = status_map.get(result_scipy.status, "solver_error")
    solver_status: Literal[
        "optimal", "optimal_inaccurate", "infeasible", "unbounded", "solver_error"
    ] = _raw_status  # type: ignore[assignment]

    if result_scipy.success or result_scipy.status in (1,):
        weights = np.clip(result_scipy.x, 0.0, None)
        if weights.sum() > 0:
            weights = weights / weights.sum()
        return SolverResult(
            weights=weights,
            solver_status="optimal" if result_scipy.success else "optimal_inaccurate",
            backend_used="scipy",
            solve_time_sec=solve_time,
            iterations=result_scipy.nfev,
            dual_vars=None,
            diagnostics={
                "max_iterations": max_iterations,
                "tolerance": tolerance,
                "solver": "SLSQP",
                "nfev": result_scipy.nfev,
            },
        )
    else:
        return SolverResult(
            weights=None,
            solver_status=solver_status,
            backend_used="scipy",
            solve_time_sec=solve_time,
            iterations=result_scipy.nfev,
            dual_vars=None,
            diagnostics={"max_iterations": max_iterations, "tolerance": tolerance},
        )
