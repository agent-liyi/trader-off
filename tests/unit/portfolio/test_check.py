"""Unit tests for portfolio.check (FR-3800).

AC-FR3800-01: check_constraints returns report with no violations for valid weights
AC-FR3800-02: artificial violations are detected (sum=0.95, max=0.12)
AC-FR3800-03: optimizer_report.json fields are present in the report
"""

import numpy as np
import pytest
from pytest import approx

from trader_off.portfolio.check import (
    CheckResult,
    ConstraintReport,
    ConstraintViolation,
    check_constraints,
    check_violations,
)
from trader_off.portfolio.constraints import OptimizerConstraints


class TestCheckConstraints:
    """Tests for check_constraints / check_violations (FR-3800)."""

    @pytest.fixture
    def valid_fixture(self):
        """10 assets with valid weights satisfying all constraints."""
        n = 10
        assets = [f"stock_{i:03d}" for i in range(n)]
        industries = ["tech", "bank", "health", "energy", "consumer"]
        industry_map = {asset: industries[i % 5] for i, asset in enumerate(assets)}
        weights = np.full(n, 1.0 / n)
        constraints = OptimizerConstraints(
            sum_to_one=True,
            long_only=True,
            max_weight=0.10,
            industry_neutral=True,
            industry_neutral_tol=0.05,
            industry_benchmark=None,
        )
        return weights, assets, industry_map, constraints

    @pytest.fixture
    def violation_fixture(self):
        """Weights that violate sum and max_weight constraints."""
        n = 10
        assets = [f"stock_{i:03d}" for i in range(n)]
        industries = ["tech", "bank", "health", "energy", "consumer"]
        industry_map = {asset: industries[i % 5] for i, asset in enumerate(assets)}
        # sum=0.95 (not full), max=0.12 (exceeds 0.10)
        weights = np.array([0.12] + [0.09] * 9 + [0.01])[:n]
        weights = weights / weights.sum() * 0.95  # sum=0.95
        weights[0] = 0.12  # exceed max
        constraints = OptimizerConstraints(
            sum_to_one=True,
            long_only=True,
            max_weight=0.10,
            industry_neutral=False,
        )
        return weights, assets, industry_map, constraints

    def test_ac_fr3800_01_no_violations(self, valid_fixture):
        """AC-FR3800-01: valid weights produce report with no violations."""
        weights, assets, industry_map, constraints = valid_fixture
        report = check_constraints(weights, assets, constraints, industry_map=industry_map)

        assert isinstance(report, ConstraintReport)
        assert len(report.violations) == 0
        assert all(check.passed for check in report.checks)

    def test_ac_fr3800_01_checks_present(self, valid_fixture):
        """AC-FR3800-01: report contains check results for each constraint type."""
        weights, assets, industry_map, constraints = valid_fixture
        report = check_constraints(weights, assets, constraints, industry_map=industry_map)

        check_names = {c.check_name for c in report.checks}
        assert "sum_to_one" in check_names
        assert "long_only" in check_names
        assert "max_weight" in check_names

    def test_ac_fr3800_02_violations_detected(self, violation_fixture):
        """AC-FR3800-02: sum=0.95 and max=0.12 violations are detected."""
        weights, assets, industry_map, constraints = violation_fixture
        report = check_constraints(weights, assets, constraints, industry_map=industry_map)

        assert len(report.violations) == 2
        violation_types = {v.type for v in report.violations}
        assert "sum_constraint" in violation_types
        assert "max_weight" in violation_types

        sum_violation = next(v for v in report.violations if v.type == "sum_constraint")
        assert sum_violation.expected == approx(1.0)
        assert sum_violation.actual == approx(0.95, abs=0.01)

        max_violation = next(v for v in report.violations if v.type == "max_weight")
        assert max_violation.expected == approx(0.10)
        assert max_violation.actual == approx(0.12, abs=0.01)

    def test_ac_fr3800_02_long_only_violation(self):
        """AC-FR3800-02: negative weight triggers long_only violation."""
        n = 5
        assets = [f"stock_{i:03d}" for i in range(n)]
        weights = np.array([-0.05, 0.25, 0.25, 0.25, 0.25])  # -5% short
        constraints = OptimizerConstraints(long_only=True, sum_to_one=True)
        report = check_constraints(weights, assets, constraints)

        long_only_violations = [v for v in report.violations if v.type == "long_only"]
        assert len(long_only_violations) == 1
        assert long_only_violations[0].asset_or_industry == "stock_000"
        assert long_only_violations[0].actual == approx(-0.05, abs=0.001)

    def test_ac_fr3800_02_severity_assignment(self, violation_fixture):
        """AC-FR3800-02: violations have severity based on magnitude."""
        weights, assets, industry_map, constraints = violation_fixture
        report = check_constraints(weights, assets, constraints, industry_map=industry_map)

        for v in report.violations:
            assert v.severity in {"low", "high"}

    def test_ac_fr3800_01_custom_industry_benchmark(self):
        """AC-FR3800-01: custom industry_benchmark is used in check."""
        n = 10
        assets = [f"stock_{i:03d}" for i in range(n)]
        industries = ["tech", "bank", "health", "energy", "consumer"]
        industry_map = {asset: industries[i % 5] for i, asset in enumerate(assets)}
        # Equal weights of 0.1 each, 2 assets per industry
        # Industry weight = 0.2 for each industry
        weights = np.full(n, 1.0 / n)
        # Custom benchmark: each asset has 0.1, so each industry sums to 0.2
        # This matches equal weights
        custom_benchmark = {assets[i]: 0.1 for i in range(n)}
        constraints = OptimizerConstraints(
            sum_to_one=True,
            long_only=True,
            max_weight=0.30,
            industry_neutral=True,
            industry_neutral_tol=0.05,
            industry_benchmark=custom_benchmark,
        )
        report = check_constraints(weights, assets, constraints, industry_map=industry_map)
        assert all(c.passed for c in report.checks)
        assert len(report.violations) == 0

    def test_ac_fr3800_03_report_fields(self, valid_fixture):
        """AC-FR3800-03: ConstraintReport has checks and violations fields."""
        weights, assets, industry_map, constraints = valid_fixture
        report = check_constraints(weights, assets, constraints, industry_map=industry_map)

        assert hasattr(report, "checks")
        assert hasattr(report, "violations")
        assert isinstance(report.checks, list)
        assert isinstance(report.violations, list)

    def test_ac_fr3800_03_check_result_fields(self, valid_fixture):
        """AC-FR3800-03: CheckResult has required fields."""
        weights, assets, industry_map, constraints = valid_fixture
        report = check_constraints(weights, assets, constraints, industry_map=industry_map)

        for check in report.checks:
            assert isinstance(check, CheckResult)
            assert check.check_name
            assert isinstance(check.passed, (bool, np.bool_))
            assert isinstance(check.actual, (float, str))
            assert isinstance(check.expected, (float, str))
            assert isinstance(check.tolerance, float)

    def test_ac_fr3800_03_violation_fields(self, violation_fixture):
        """AC-FR3800-03: ConstraintViolation has required fields."""
        weights, assets, industry_map, constraints = violation_fixture
        report = check_constraints(weights, assets, constraints, industry_map=industry_map)

        for v in report.violations:
            assert isinstance(v, ConstraintViolation)
            assert v.type in {"sum_constraint", "max_weight", "long_only", "industry_neutral"}
            assert isinstance(v.expected, float)
            assert isinstance(v.actual, float)
            assert v.severity in {"low", "high"}

    def test_ac_fr3800_01_industry_neutral_check(self):
        """AC-FR3800-01: industry neutral check passes when weights match benchmark."""
        n = 10
        assets = [f"stock_{i:03d}" for i in range(n)]
        industries = ["tech", "bank", "health", "energy", "consumer"]
        industry_map = {asset: industries[i % 5] for i, asset in enumerate(assets)}
        # Equal weights, equal benchmark per industry
        weights = np.full(n, 1.0 / n)
        constraints = OptimizerConstraints(
            sum_to_one=True,
            long_only=True,
            max_weight=0.20,
            industry_neutral=True,
            industry_neutral_tol=0.05,
            industry_benchmark=None,
        )
        report = check_constraints(weights, assets, constraints, industry_map=industry_map)

        industry_checks = [c for c in report.checks if c.check_name.startswith("industry_neutral_")]
        assert len(industry_checks) == 5
        assert all(c.passed for c in industry_checks)

    def test_ac_fr3800_02_industry_neutral_violation(self):
        """AC-FR3800-02: industry neutral violation is detected with severity."""
        n = 10
        assets = [f"stock_{i:03d}" for i in range(n)]
        industries = ["tech", "bank", "health", "energy", "consumer"]
        industry_map = {asset: industries[i % 5] for i, asset in enumerate(assets)}
        # Tech gets 50%, others get 12.5% each
        weights = np.array([0.50] + [0.125] * 9)
        constraints = OptimizerConstraints(
            sum_to_one=True,
            long_only=True,
            max_weight=0.50,
            industry_neutral=True,
            industry_neutral_tol=0.05,
            industry_benchmark=None,
        )
        report = check_constraints(weights, assets, constraints, industry_map=industry_map)

        industry_violations = [v for v in report.violations if v.type == "industry_neutral"]
        assert len(industry_violations) == 1
        assert industry_violations[0].asset_or_industry == "tech"
        assert industry_violations[0].severity == "high"

    def test_check_violations_alias(self, valid_fixture):
        """FR-3800: check_violations is an alias for check_constraints."""
        weights, assets, industry_map, constraints = valid_fixture
        report1 = check_constraints(weights, assets, constraints, industry_map=industry_map)
        report2 = check_violations(weights, assets, constraints, industry_map=industry_map)

        assert len(report1.violations) == len(report2.violations)
        assert all(c1.passed == c2.passed for c1, c2 in zip(report1.checks, report2.checks))
