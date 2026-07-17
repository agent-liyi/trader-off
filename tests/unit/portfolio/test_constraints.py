"""Unit tests for portfolio.constraints (FR-3300, FR-3400).

FR-3300 (full-position): full_position_constraint returns Σw=1 spec
FR-3400 (long-only): long_only_constraint returns w_i >= 0 bounds spec
"""

import numpy as np


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
