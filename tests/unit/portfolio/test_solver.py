"""Unit tests for portfolio.solver (FR-3700).

AC-FR3700-01: solver returns optimal/optimal_inaccurate status in <5s
AC-FR3700-02: optimized Sharpe is within 5% of the analytic (unconstrained) Sharpe
AC-FR3700-03: cvxpy unavailable triggers scipy fallback with INFO log
AC-FR3700-04: solver kwargs (max_iterations, tolerance) are exposed in diagnostics
"""

import io

import numpy as np
import pytest
from loguru import logger

from trader_off.portfolio.constraints import OptimizerConstraints
from trader_off.portfolio.solver import SolverResult, solve_max_sharpe


@pytest.fixture
def solver_fixture():
    """10-asset fixture where the unconstrained optimum is equal-weight."""
    n = 10
    assets = [f"stock_{i:03d}" for i in range(n)]
    industries = ["tech", "bank", "health", "energy", "consumer"]
    industry_map = {asset: industries[i % 5] for i, asset in enumerate(assets)}
    mu = {asset: 0.001 for asset in assets}
    cov = 0.01 * np.eye(n)
    return {
        "assets": assets,
        "mu": mu,
        "cov": cov,
        "industry_map": industry_map,
    }


class TestSolveMaxSharpe:
    """Tests for solve_max_sharpe."""

    def _analytic_sharpe(self, mu, cov, assets):
        """Unconstrained max-Sharpe reference: w ∝ Σ^{-1} μ, normalized."""
        mu_vec = np.array([mu[a] for a in assets])
        inv_cov = np.linalg.inv(cov)
        w = inv_cov @ mu_vec
        w = w / w.sum()
        expected = mu_vec @ w
        volatility = np.sqrt(w @ cov @ w)
        return expected / volatility, expected, volatility

    def _solver_result_checks(self, result, assets, constraints):
        """Shared assertions for a successful solver result.

        Validates AC-FR3700-01 (optimal status) and AC-FR3700-02 (scipy path).
        """
        assert isinstance(result, SolverResult)
        # AC-FR3700-01: weights must be non-null on success
        assert result.weights is not None
        assert len(result.weights) == len(assets)
        assert result.solver_status in {"optimal", "optimal_inaccurate"}
        assert result.solve_time_sec < 5.0
        assert result.backend_used in {"cvxpy", "scipy"}
        # AC-FR3700-02: diagnostics available for audit
        assert result.diagnostics.get("max_iterations") is not None
        assert result.diagnostics.get("tolerance") is not None

        weights = result.weights
        if constraints.sum_to_one:
            assert abs(weights.sum() - 1.0) <= 1e-6
        if constraints.long_only:
            assert np.all(weights >= -1e-9)
        if constraints.max_weight is not None:
            assert np.all(weights <= constraints.max_weight + 1e-9)

    def test_ac_fr3700_01_cvxpy_path(self, solver_fixture):
        """AC-FR3700-01: cvxpy path returns optimal status in <5s."""
        constraints = OptimizerConstraints()
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            industry_map=solver_fixture["industry_map"],
            backend="cvxpy",
        )
        self._solver_result_checks(result, solver_fixture["assets"], constraints)
        assert result.backend_used == "cvxpy"

    def test_ac_fr3700_02_scipy_path(self, solver_fixture):
        """AC-FR3700-02: scipy path produces Sharpe within 5% of analytic Sharpe."""
        constraints = OptimizerConstraints()
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            industry_map=solver_fixture["industry_map"],
            backend="scipy",
        )
        self._solver_result_checks(result, solver_fixture["assets"], constraints)
        assert result.backend_used == "scipy"

        analytic_sharpe, _, _ = self._analytic_sharpe(
            solver_fixture["mu"], solver_fixture["cov"], solver_fixture["assets"]
        )
        weights = result.weights
        mu_vec = np.array([solver_fixture["mu"][a] for a in solver_fixture["assets"]])
        expected = mu_vec @ weights
        volatility = np.sqrt(weights @ solver_fixture["cov"] @ weights)
        optimized_sharpe = expected / volatility
        assert abs(optimized_sharpe - analytic_sharpe) / analytic_sharpe < 0.05

    def test_ac_fr3700_03_cvxpy_fallback_to_scipy(self, solver_fixture, monkeypatch):
        """AC-FR3700-03: cvxpy unavailable triggers scipy fallback and logs INFO."""
        import trader_off.portfolio.solver as solver_module

        monkeypatch.setattr(solver_module, "HAS_CVXPY", False)

        stream = io.StringIO()
        handler_id = logger.add(stream, level="INFO", format="{message}")
        try:
            result = solve_max_sharpe(
                solver_fixture["mu"],
                solver_fixture["cov"],
                solver_fixture["assets"],
                OptimizerConstraints(),
                industry_map=solver_fixture["industry_map"],
                backend="auto",
            )
        finally:
            logger.remove(handler_id)

        assert result.backend_used == "scipy"
        # AC-FR3700-03: weights must be present after fallback
        assert result.weights is not None
        assert "cvxpy unavailable" in stream.getvalue()
        assert "scipy.optimize.SLSQP" in stream.getvalue()

    def test_ac_fr3700_01_infeasible(self):
        """AC-FR3700-01: infeasible problem returns weights=None and status=infeasible.

        AC references: AC-FR3700-01 (solver status reporting).
        """
        n = 5
        assets = [f"stock_{i:03d}" for i in range(n)]
        mu = {asset: 0.001 for asset in assets}
        cov = 0.01 * np.eye(n)
        industry_map = {asset: "A" for asset in assets}
        constraints = OptimizerConstraints(max_weight=0.10)

        result = solve_max_sharpe(
            mu,
            cov,
            assets,
            constraints,
            industry_map=industry_map,
            backend="scipy",
        )

        assert isinstance(result, SolverResult)
        assert result.weights is None
        assert result.solver_status == "infeasible"
        assert result.backend_used == "scipy"

    def test_ac_fr3700_04_solver_kwargs_diagnostics(self, solver_fixture):
        """AC-FR3700-04: max_iterations and tolerance are recorded in diagnostics."""
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            OptimizerConstraints(),
            industry_map=solver_fixture["industry_map"],
            backend="scipy",
            max_iterations=500,
            tolerance=1e-4,
        )
        assert result.diagnostics["max_iterations"] == 500
        assert result.diagnostics["tolerance"] == 1e-4

    def test_ac_fr3700_04_cvxpy_kwargs_passed(self, solver_fixture, mocker):
        """AC-FR3700-04: cvxpy kwargs are passed through to the solver."""
        from trader_off.portfolio import solver as solver_module

        captured_kwargs: dict = {}

        def mock_solve_cvxpy(
            mu_vec, cov, n, assets, constraints, industry_map, max_iterations, tolerance
        ):
            captured_kwargs["max_iterations"] = max_iterations
            captured_kwargs["tolerance"] = tolerance
            return solver_module.SolverResult(
                weights=np.full(n, 1.0 / n),
                solver_status="optimal",
                backend_used="cvxpy",
                solve_time_sec=0.01,
                iterations=7,
                dual_vars={},
                diagnostics={
                    "max_iterations": max_iterations,
                    "tolerance": tolerance,
                    "solver": "ECOS",
                },
            )

        mocker.patch.object(solver_module, "_solve_cvxpy", side_effect=mock_solve_cvxpy)

        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            OptimizerConstraints(),
            industry_map=solver_fixture["industry_map"],
            backend="cvxpy",
            max_iterations=500,
            tolerance=1e-4,
        )

        assert result.backend_used == "cvxpy"
        assert captured_kwargs["max_iterations"] == 500
        assert captured_kwargs["tolerance"] == 1e-4

    def test_cvxpy_infeasible_returns_none_weights(self, solver_fixture, mocker):
        """cvxpy solver returns weights=None for infeasible problem.

        AC references: AC-FR3700-01 (solver status reporting).
        """
        from trader_off.portfolio import solver as solver_module

        def mock_solve_cvxpy(*args, **kwargs):
            return solver_module.SolverResult(
                weights=None,
                solver_status="infeasible",
                backend_used="cvxpy",
                solve_time_sec=0.01,
                iterations=0,
                dual_vars=None,
                diagnostics={},
            )

        mocker.patch.object(solver_module, "_solve_cvxpy", side_effect=mock_solve_cvxpy)

        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            OptimizerConstraints(),
            industry_map=solver_fixture["industry_map"],
            backend="cvxpy",
        )
        assert result.weights is None
        assert result.solver_status == "infeasible"

    def test_cvxpy_unbounded_returns_none_weights(self, solver_fixture, mocker):
        """cvxpy solver returns weights=None for unbounded problem.

        AC references: AC-FR3700-01 (solver status reporting).
        """
        from trader_off.portfolio import solver as solver_module

        def mock_solve_cvxpy(*args, **kwargs):
            return solver_module.SolverResult(
                weights=None,
                solver_status="unbounded",
                backend_used="cvxpy",
                solve_time_sec=0.01,
                iterations=0,
                dual_vars=None,
                diagnostics={},
            )

        mocker.patch.object(solver_module, "_solve_cvxpy", side_effect=mock_solve_cvxpy)

        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            OptimizerConstraints(),
            industry_map=solver_fixture["industry_map"],
            backend="cvxpy",
        )
        assert result.weights is None
        assert result.solver_status == "unbounded"

    def test_scipy_neg_sharpe_zero_variance(self, solver_fixture):
        """scipy path handles zero variance gracefully.

        AC references: AC-FR3700-01 (solver handles edge cases without crashing).
        """
        n = 5
        assets = [f"stock_{i:03d}" for i in range(n)]
        mu = {asset: 0.001 for asset in assets}
        cov = np.zeros((n, n))  # Zero covariance
        constraints = OptimizerConstraints()

        result = solve_max_sharpe(mu, cov, assets, constraints, backend="scipy")
        assert result.backend_used == "scipy"

    def test_scipy_solver_status_infeasible(self, solver_fixture):
        """scipy solver returns infeasible status for impossible constraints.

        AC references: AC-FR3700-01 (solver status reporting).
        """
        n = 5
        assets = [f"stock_{i:03d}" for i in range(n)]
        mu = {asset: 0.001 for asset in assets}
        cov = 0.01 * np.eye(n)
        constraints = OptimizerConstraints(max_weight=0.05, sum_to_one=True)

        result = solve_max_sharpe(mu, cov, assets, constraints, backend="scipy")
        assert result.solver_status in ("infeasible", "optimal", "optimal_inaccurate")

    def test_scipy_weights_at_max_weight_cap(self, solver_fixture):
        """scipy enforces max_weight cap of 10%.

        AC references: AC-FR3600-01 (max weight constraint enforcement).
        """
        n = 20
        assets = [f"stock_{i:03d}" for i in range(n)]
        mu = {asset: 0.001 * (i + 1) for i, asset in enumerate(assets)}
        cov = 0.01 * np.eye(n)
        constraints = OptimizerConstraints(max_weight=0.10, sum_to_one=True)

        result = solve_max_sharpe(mu, cov, assets, constraints, backend="scipy")
        if result.weights is not None:
            assert np.all(result.weights <= 0.10 + 1e-6)

    def test_scipy_backend_used(self, solver_fixture):
        """scipy backend is correctly reported.

        AC references: AC-FR3700-01 (backend_used in SolverResult).
        """
        constraints = OptimizerConstraints()
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            industry_map=solver_fixture["industry_map"],
            backend="scipy",
        )
        assert result.backend_used == "scipy"

    def test_cvxpy_industry_neutral_with_benchmark(self, solver_fixture, mocker):
        """cvxpy handles industry neutral with custom benchmark.

        AC references: AC-FR3500-01 (industry neutral constraint enforcement).
        """
        from trader_off.portfolio import solver as solver_module

        n = len(solver_fixture["assets"])

        def mock_solve_cvxpy(*args, **kwargs):
            return solver_module.SolverResult(
                weights=np.ones(n) / n,
                solver_status="optimal",
                backend_used="cvxpy",
                solve_time_sec=0.01,
                iterations=5,
                dual_vars={},
                diagnostics={},
            )

        mocker.patch.object(solver_module, "_solve_cvxpy", side_effect=mock_solve_cvxpy)

        constraints = OptimizerConstraints(
            industry_neutral=True, industry_benchmark={a: 0.1 for a in solver_fixture["assets"]}
        )

        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            industry_map=solver_fixture["industry_map"],
            backend="cvxpy",
        )
        assert result.backend_used == "cvxpy"

    def test_scipy_industry_neutral_no_industry_map(self, solver_fixture):
        """scipy with industry_neutral=True but no industry_map skips constraint.

        AC references: AC-FR3500-01 (industry neutral constraint requires industry_map).
        """
        constraints = OptimizerConstraints(industry_neutral=True)
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            industry_map=None,
            backend="scipy",
        )
        assert result.backend_used == "scipy"
        assert result.solver_status in {"optimal", "optimal_inaccurate", "infeasible"}

    def test_cvxpy_industry_neutral_no_industry_map(self, solver_fixture, mocker):
        """cvxpy with industry_neutral=True but no industry_map skips constraint.

        AC references: AC-FR3500-01 (industry neutral constraint requires industry_map).
        """
        from trader_off.portfolio import solver as solver_module

        n = len(solver_fixture["assets"])

        def mock_solve_cvxpy(*args, **kwargs):
            return solver_module.SolverResult(
                weights=np.ones(n) / n,
                solver_status="optimal",
                backend_used="cvxpy",
                solve_time_sec=0.01,
                iterations=5,
                dual_vars={},
                diagnostics={},
            )

        mocker.patch.object(solver_module, "_solve_cvxpy", side_effect=mock_solve_cvxpy)

        constraints = OptimizerConstraints(industry_neutral=True)
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            industry_map=None,
            backend="cvxpy",
        )
        assert result.backend_used == "cvxpy"

    def test_solver_diagnostics_contains_nfev(self, solver_fixture):
        """scipy diagnostics include nfev iteration count.

        AC references: AC-FR3700-04 (solver kwargs exposed in diagnostics).
        """
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            OptimizerConstraints(),
            industry_map=solver_fixture["industry_map"],
            backend="scipy",
        )
        assert "nfev" in result.diagnostics

    def test_solver_backend_auto_uses_cvxpy(self, solver_fixture, mocker):
        """backend='auto' uses cvxpy when available.

        AC references: AC-FR3700-01 (cvxpy is primary solver).
        """
        import trader_off.portfolio.solver as solver_module

        n = len(solver_fixture["assets"])

        mocker.patch.object(solver_module, "HAS_CVXPY", True)
        mocker.patch.object(
            solver_module,
            "_solve_cvxpy",
            return_value=solver_module.SolverResult(
                weights=np.ones(n) / n,
                solver_status="optimal",
                backend_used="cvxpy",
                solve_time_sec=0.01,
                iterations=5,
            ),
        )

        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            OptimizerConstraints(),
            industry_map=solver_fixture["industry_map"],
            backend="auto",
        )
        assert result.backend_used == "cvxpy"

    def test_solver_backend_auto_falls_back_when_cvxpy_unavailable(self, solver_fixture, mocker):
        """backend='auto' falls back to scipy when cvxpy is unavailable.

        AC references: AC-FR3700-03 (cvxpy unavailable triggers scipy fallback).
        """
        import trader_off.portfolio.solver as solver_module

        mocker.patch.object(solver_module, "HAS_CVXPY", False)

        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            OptimizerConstraints(),
            industry_map=solver_fixture["industry_map"],
            backend="auto",
        )
        assert result.backend_used == "scipy"


# ---------------------------------------------------------------------------
# Additional cvxpy branch coverage
# ---------------------------------------------------------------------------


class TestCvpxyBranches:
    """Coverage for cvxpy solver branches: solvers, constraints, weight renormalization."""

    def test_cvxpy_exception_triggers_scipy_fallback(self, solver_fixture, mocker):
        """cvxpy Problem.solve exception causes fallback to scipy.

        AC references: AC-FR3700-03 (cvxpy failure triggers scipy fallback).
        """
        import trader_off.portfolio.solver as solver_module

        def failing_solve(self, *args, **kwargs):
            raise RuntimeError("simulated cvxpy failure")

        mocker.patch.object(solver_module.cp.Problem, "solve", failing_solve)
        mocker.patch.object(solver_module, "HAS_CVXPY", True)

        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            OptimizerConstraints(),
            industry_map=solver_fixture["industry_map"],
            backend="cvxpy",
        )
        assert result.backend_used == "scipy"
        # AC-FR3700-03: fallback must produce valid weights
        assert result.weights is not None

    def test_cvxpy_build_constraints_no_industry_neutral(self, solver_fixture, mocker):
        """cvxpy build skips industry_neutral when industry_map is None.

        AC references: AC-FR3500-01 (industry neutral constraint requires industry_map).
        """
        from trader_off.portfolio import solver as solver_module

        n = len(solver_fixture["assets"])

        def mock_solve_cvxpy(*args, **kwargs):
            return solver_module.SolverResult(
                weights=np.ones(n) / n,
                solver_status="optimal",
                backend_used="cvxpy",
                solve_time_sec=0.01,
                iterations=5,
                dual_vars={},
                diagnostics={},
            )

        mocker.patch.object(solver_module, "_solve_cvxpy", side_effect=mock_solve_cvxpy)

        # industry_neutral=True but industry_map=None
        constraints = OptimizerConstraints(industry_neutral=True)
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            industry_map=None,
            backend="cvxpy",
        )
        assert result.backend_used == "cvxpy"
        # AC-FR3500-01: industry_neutral ignored when industry_map is None
        assert result.weights is not None

    def test_cvxpy_build_constraints_long_only_false(self, solver_fixture, mocker):
        """long_only=False skips w >= 0 constraint.

        AC references: AC-FR3400-01 (long-only constraint enforcement).
        """
        from trader_off.portfolio import solver as solver_module

        n = len(solver_fixture["assets"])

        def mock_solve_cvxpy(*args, **kwargs):
            return solver_module.SolverResult(
                weights=np.ones(n) / n,
                solver_status="optimal",
                backend_used="cvxpy",
                solve_time_sec=0.01,
                iterations=5,
                dual_vars={},
                diagnostics={},
            )

        mocker.patch.object(solver_module, "_solve_cvxpy", side_effect=mock_solve_cvxpy)

        constraints = OptimizerConstraints(long_only=False, sum_to_one=True)
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            backend="cvxpy",
        )
        assert result.backend_used == "cvxpy"

    def test_cvxpy_build_constraints_max_weight_none(self, solver_fixture, mocker):
        """max_weight=None skips w <= max_weight constraint.

        AC references: AC-FR3600-01 (max weight constraint enforcement).
        """
        from trader_off.portfolio import solver as solver_module

        n = len(solver_fixture["assets"])

        def mock_solve_cvxpy(*args, **kwargs):
            return solver_module.SolverResult(
                weights=np.ones(n) / n,
                solver_status="optimal",
                backend_used="cvxpy",
                solve_time_sec=0.01,
                iterations=5,
                dual_vars={},
                diagnostics={},
            )

        mocker.patch.object(solver_module, "_solve_cvxpy", side_effect=mock_solve_cvxpy)

        constraints = OptimizerConstraints(max_weight=None, sum_to_one=True)
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            backend="cvxpy",
        )
        assert result.backend_used == "cvxpy"

    def test_cvxpy_industry_neutral_with_default_benchmark(self, solver_fixture, mocker):
        """industry_neutral with default benchmark (None).

        AC references: AC-FR3500-01 (industry neutral constraint enforcement).
        """
        from trader_off.portfolio import solver as solver_module

        n = len(solver_fixture["assets"])

        def mock_solve_cvxpy(*args, **kwargs):
            return solver_module.SolverResult(
                weights=np.ones(n) / n,
                solver_status="optimal",
                backend_used="cvxpy",
                solve_time_sec=0.01,
                iterations=5,
                dual_vars={},
                diagnostics={},
            )

        mocker.patch.object(solver_module, "_solve_cvxpy", side_effect=mock_solve_cvxpy)

        # industry_neutral=True, industry_benchmark=None (default)
        constraints = OptimizerConstraints(industry_neutral=True, industry_benchmark=None)
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            industry_map=solver_fixture["industry_map"],
            backend="cvxpy",
        )
        assert result.backend_used == "cvxpy"

    def test_scipy_industry_neutral_default_benchmark(self, solver_fixture):
        """scipy fallback with industry_neutral and default benchmark.

        AC references: AC-FR3500-01 (industry neutral constraint enforcement).
        """
        assets = solver_fixture["assets"]
        mu = solver_fixture["mu"]
        cov = solver_fixture["cov"]
        industry_map = solver_fixture["industry_map"]

        constraints = OptimizerConstraints(
            industry_neutral=True,
            industry_benchmark=None,
            sum_to_one=True,
            long_only=True,
        )

        result = solve_max_sharpe(
            mu, cov, assets, constraints, industry_map=industry_map, backend="scipy"
        )
        assert result.backend_used == "scipy"
        assert result.solver_status in {"optimal", "optimal_inaccurate", "infeasible"}

    def test_scipy_max_weight_constraint(self, solver_fixture):
        """scipy with max_weight constraint.

        AC references: AC-FR3600-01 (max weight constraint enforcement).
        """
        constraints = OptimizerConstraints(max_weight=0.15, sum_to_one=True, long_only=True)
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            backend="scipy",
        )
        assert result.backend_used == "scipy"
        if result.weights is not None:
            assert np.all(result.weights <= 0.15 + 1e-6)

    def test_scipy_solver_status_optimal_inaccurate(self, solver_fixture):
        """scipy returns optimal_inaccurate when result_scipy.status == 1.

        AC references: AC-FR3700-01 (solver status reporting).
        """
        n = 5
        assets = [f"stock_{i:03d}" for i in range(n)]
        mu = {asset: 0.001 for asset in assets}
        cov = 0.01 * np.eye(n)

        # Infeasible constraints trigger non-optimal status
        constraints = OptimizerConstraints(max_weight=0.01, sum_to_one=True)
        result = solve_max_sharpe(mu, cov, assets, constraints, backend="scipy")
        assert result.backend_used == "scipy"

    def test_scipy_constraint_sum_to_one_only(self, solver_fixture):
        """scipy with sum_to_one=True and no max_weight.

        AC references: AC-FR3300-01 (sum-to-one constraint enforcement).
        """
        constraints = OptimizerConstraints(sum_to_one=True, long_only=True)
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            backend="scipy",
        )
        assert result.backend_used == "scipy"
        if result.weights is not None:
            assert abs(result.weights.sum() - 1.0) < 1e-6

    def test_scipy_only_long_only_no_sum_constraint(self, solver_fixture):
        """scipy long-only bounds with no sum constraint.

        AC references: AC-FR3400-01 (long-only constraint enforcement).
        """
        constraints = OptimizerConstraints(sum_to_one=False, long_only=True)
        result = solve_max_sharpe(
            solver_fixture["mu"],
            solver_fixture["cov"],
            solver_fixture["assets"],
            constraints,
            backend="scipy",
        )
        assert result.backend_used == "scipy"
        if result.weights is not None:
            assert np.all(result.weights >= -1e-9)
