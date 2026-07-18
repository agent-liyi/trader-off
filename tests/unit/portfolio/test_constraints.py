"""Unit tests for portfolio.constraints (FR-3300, FR-3400).

FR-3300 (full-position): full_position_constraint returns Σw=1 spec
FR-3400 (long-only): long_only_constraint returns w_i >= 0 bounds spec
"""

import numpy as np
import pytest
from pytest import approx


class TestFullPositionConstraint:
    """Tests for full_position_constraint (FR-3300)."""

    def test_ac_fr3300_01_sum_to_one_spec(self):
        """FR-3300: returns constraint spec a_eq=ones, b_eq=1 for Σw=1."""
        from trader_off.portfolio.constraints import full_position_constraint

        n = 10
        a_eq, b_eq = full_position_constraint(n)
        assert a_eq.shape == (1, n)
        assert np.allclose(a_eq, 1.0)
        assert np.allclose(b_eq, [1.0])

        # Verify the constraint is correct: Σw = 1
        w = np.ones(n) / n  # equal weight
        assert np.allclose(a_eq @ w, b_eq)

    def test_ac_fr3300_01_different_sizes(self):
        """FR-3300: works for various portfolio sizes."""
        from trader_off.portfolio.constraints import full_position_constraint

        for n in [1, 5, 50, 100]:
            a_eq, b_eq = full_position_constraint(n)
            assert a_eq.shape == (1, n)
            assert b_eq.shape == (1,)


class TestLongOnlyConstraint:
    """Tests for long_only_constraint (FR-3400)."""

    def test_ac_fr3400_01_bounds_spec(self):
        """FR-3400: returns bounds with lb=0 for all assets."""
        from trader_off.portfolio.constraints import long_only_constraint

        n = 10
        lb, ub = long_only_constraint(n)
        assert lb.shape == (n,)
        assert ub.shape == (n,)
        assert np.allclose(lb, 0.0)
        assert np.all(np.isinf(ub))

    def test_ac_fr3400_01_different_sizes(self):
        """FR-3400: works for various portfolio sizes."""
        from trader_off.portfolio.constraints import long_only_constraint

        for n in [1, 5, 50, 100]:
            lb, ub = long_only_constraint(n)
            assert lb.shape == (n,)
            assert ub.shape == (n,)


class TestIndustryNeutralConstraint:
    """Tests for industry_neutral_constraint (FR-3500)."""

    @pytest.fixture
    def industry_neutral_fixture(self):
        """25 assets across 5 equal industries with equal benchmark weights."""
        tickers = [f"stock_{i:03d}" for i in range(25)]
        industries = ["tech", "bank", "health", "energy", "consumer"]
        industry_map = {ticker: industries[i // 5] for i, ticker in enumerate(tickers)}
        benchmark_weights = {ticker: 1.0 / len(tickers) for ticker in tickers}
        return tickers, industry_map, benchmark_weights

    def test_ac_fr3500_01_equality_constraint_spec(self, industry_neutral_fixture):
        """AC-FR3500-01: returns A_eq/b_eq enforcing Σ(w_i - benchmark_i)=0 per industry."""
        from trader_off.portfolio.constraints import industry_neutral_constraint

        tickers, industry_map, benchmark_weights = industry_neutral_fixture
        a_eq, b_eq = industry_neutral_constraint(tickers, industry_map, benchmark_weights)

        assert a_eq.shape == (5, 25)
        assert b_eq.shape == (5,)
        assert np.allclose(a_eq.sum(axis=1), 5.0)

        ticker_index = {t: i for i, t in enumerate(tickers)}
        for industry in set(industry_map.values()):
            j = sorted(set(industry_map.values())).index(industry)
            industry_assets = [t for t in tickers if industry_map[t] == industry]
            for t in tickers:
                idx = ticker_index[t]
                if t in industry_assets:
                    assert a_eq[j, idx] == approx(1.0)
                else:
                    assert a_eq[j, idx] == approx(0.0)
            expected_b = sum(benchmark_weights[t] for t in industry_assets)
            assert b_eq[j] == approx(expected_b)

        # Verify the equality holds for equal weights equal to benchmark
        w = np.array([benchmark_weights[t] for t in tickers])
        assert np.allclose(a_eq @ w, b_eq)

    def test_ac_fr3500_01_different_benchmark(self):
        """FR-3500: custom benchmark weights are reflected in b_eq."""
        from trader_off.portfolio.constraints import industry_neutral_constraint

        tickers = ["a1", "a2", "b1"]
        industry_map = {"a1": "A", "a2": "A", "b1": "B"}
        benchmark_weights = {"a1": 0.3, "a2": 0.1, "b1": 0.2}
        a_eq, b_eq = industry_neutral_constraint(tickers, industry_map, benchmark_weights)

        assert a_eq.shape == (2, 3)
        assert b_eq[0] == approx(0.4)
        assert b_eq[1] == approx(0.2)

    def test_ac_fr3500_03_missing_ticker_raises(self):
        """FR-3500: tickers missing from inputs raise ValueError."""
        from trader_off.portfolio.constraints import industry_neutral_constraint

        tickers = ["a1", "a2", "b1"]
        industry_map = {"a1": "A", "a2": "A"}
        benchmark_weights = {"a1": 0.3, "a2": 0.1, "b1": 0.2}

        with pytest.raises(ValueError, match="industry_map"):
            industry_neutral_constraint(tickers, industry_map, benchmark_weights)

        industry_map = {"a1": "A", "a2": "A", "b1": "B"}
        benchmark_weights = {"a1": 0.3, "a2": 0.1}
        with pytest.raises(ValueError, match="benchmark_weights"):
            industry_neutral_constraint(tickers, industry_map, benchmark_weights)
