"""Post-solve constraint violation detection and reporting (FR-3800).

Provides `check_constraints` and `check_violations` which validate that a
set of portfolio weights satisfies all constraints and return a
`ConstraintReport` listing any violations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class CheckResult:
    """Result of a single constraint check.

    Attributes:
        check_name: Human-readable name of the check (e.g. "sum_to_one").
        passed: True if the constraint is satisfied, False otherwise.
        actual: Observed value (e.g., the actual sum of weights).
        expected: Expected value (e.g., 1.0 for sum_to_one).
        tolerance: Numerical tolerance used in the comparison.
    """

    check_name: str
    passed: bool
    actual: float | str
    expected: float | str
    tolerance: float


@dataclass(frozen=True)
class ConstraintViolation:
    """A single violated constraint.

    Attributes:
        type: Constraint type identifier.
        asset_or_industry: Asset ticker or industry name if applicable.
        expected: The expected value / limit.
        actual: The observed value that violated the constraint.
        severity: "low" or "high".
    """

    type: Literal["sum_constraint", "max_weight", "long_only", "industry_neutral"]
    asset_or_industry: str | None
    expected: float
    actual: float
    severity: Literal["low", "high"]


@dataclass(frozen=True)
class ConstraintReport:
    """Report of all constraint checks and violations.

    Attributes:
        checks: List of individual check results.
        violations: List of violated constraints (may be empty).
    """

    checks: list[CheckResult]
    violations: list[ConstraintViolation]


def check_violations(
    weights: np.ndarray,
    assets: list[str],
    constraints,
    industry_map: dict[str, str] | None = None,
) -> ConstraintReport:
    """Check a weight vector for constraint violations.

    Args:
        weights: Asset weights (length N).
        assets: Ordered list of asset identifiers (length N).
        constraints: OptimizerConstraints dataclass.
        industry_map: Optional mapping from asset -> industry name.

    Returns:
        ConstraintReport with per-check results and a list of violations.
    """
    n = len(weights)
    checks: list[CheckResult] = []
    violations: list[ConstraintViolation] = []

    # 1. Sum-to-one check
    sum_tol = 1e-6
    sum_actual = weights.sum()
    sum_passed = abs(sum_actual - 1.0) <= sum_tol
    checks.append(
        CheckResult(
            check_name="sum_to_one",
            passed=sum_passed,
            actual=float(sum_actual),
            expected=1.0,
            tolerance=sum_tol,
        )
    )
    if not sum_passed:
        severity: Literal["low", "high"] = "high" if abs(sum_actual - 1.0) > 0.01 else "low"
        violations.append(
            ConstraintViolation(
                type="sum_constraint",
                asset_or_industry=None,
                expected=1.0,
                actual=float(sum_actual),
                severity=severity,
            )
        )

    # 2. Long-only check
    long_tol = 1e-9
    min_weight = weights.min()
    long_passed = min_weight >= -long_tol
    checks.append(
        CheckResult(
            check_name="long_only",
            passed=long_passed,
            actual=float(min_weight),
            expected=0.0,
            tolerance=long_tol,
        )
    )
    if not long_passed:
        worst_idx = int(np.argmin(weights))
        violations.append(
            ConstraintViolation(
                type="long_only",
                asset_or_industry=assets[worst_idx],
                expected=0.0,
                actual=float(weights[worst_idx]),
                severity="high" if weights[worst_idx] < -1e-6 else "low",
            )
        )

    # 3. Max-weight check
    if constraints.max_weight is not None:
        max_tol = 1e-9
        max_weight = weights.max()
        max_passed = max_weight <= constraints.max_weight + max_tol
        checks.append(
            CheckResult(
                check_name="max_weight",
                passed=max_passed,
                actual=float(max_weight),
                expected=float(constraints.max_weight),
                tolerance=max_tol,
            )
        )
        if not max_passed:
            worst_idx = int(np.argmax(weights))
            violations.append(
                ConstraintViolation(
                    type="max_weight",
                    asset_or_industry=assets[worst_idx],
                    expected=float(constraints.max_weight),
                    actual=float(weights[worst_idx]),
                    severity="high"
                    if weights[worst_idx] > constraints.max_weight + 1e-4
                    else "low",
                )
            )

    # 4. Industry neutral check
    if constraints.industry_neutral and industry_map is not None:
        industries = sorted(set(industry_map.values()))
        for industry in industries:
            industry_mask = np.array(
                [1.0 if industry_map.get(a) == industry else 0.0 for a in assets]
            )
            industry_weight = float(np.dot(industry_mask, weights))
            benchmark = constraints.industry_benchmark
            if benchmark is None:
                expected_b = 1.0 / len(industries)
            else:
                expected_b = sum(
                    benchmark.get(a, 1.0 / n) for a in assets if industry_map.get(a) == industry
                )

            tol = constraints.industry_neutral_tol + 1e-6
            industry_passed = abs(industry_weight - expected_b) <= tol
            checks.append(
                CheckResult(
                    check_name=f"industry_neutral_{industry}",
                    passed=industry_passed,
                    actual=industry_weight,
                    expected=expected_b,
                    tolerance=tol,
                )
            )
            if not industry_passed:
                violations.append(
                    ConstraintViolation(
                        type="industry_neutral",
                        asset_or_industry=industry,
                        expected=expected_b,
                        actual=industry_weight,
                        severity="high" if abs(industry_weight - expected_b) > 0.02 else "low",
                    )
                )

    return ConstraintReport(checks=checks, violations=violations)


def check_constraints(
    weights: np.ndarray,
    assets: list[str],
    constraints,
    industry_map: dict[str, str] | None = None,
) -> ConstraintReport:
    """Alias for check_violations (FR-3800 interface).

    Args:
        weights: Asset weights (length N).
        assets: Ordered list of asset identifiers (length N).
        constraints: OptimizerConstraints dataclass.
        industry_map: Optional mapping from asset -> industry name.

    Returns:
        ConstraintReport with per-check results and a list of violations.
    """
    return check_violations(weights, assets, constraints, industry_map=industry_map)
