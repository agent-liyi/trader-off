"""Unit tests for portfolio.baseline (FR-3900: equal-weight baseline comparison).

AC-FR3900-01: compare_to_baseline returns ComparisonReport with optimized/equal_weight dicts
AC-FR3900-02: first run turnover = 0.5 (w_prev = 0)
AC-FR3900-03: optimized sharpe < baseline → WARNING log, not error
"""

import numpy as np
import pytest
from loguru import logger

from trader_off.portfolio.baseline import (
    ComparisonReport,
    compare_to_baseline,
    equal_weight_portfolio,
)


class TestEqualWeightPortfolio:
    """Tests for equal_weight_portfolio."""

    def test_ac_fr3900_01_equal_weight_sum(self):
        """AC-FR3900-01: equal_weight_portfolio returns uniform 1/N weights summing to 1."""
        tickers = [f"stock_{i:03d}" for i in range(50)]
        weights = equal_weight_portfolio(tickers)
        assert weights.shape == (50,)
        assert np.allclose(weights.sum(), 1.0, atol=1e-9)
        assert np.allclose(weights, 1.0 / 50)

    def test_ac_fr3900_01_equal_weight_single(self):
        """AC-FR3900-01: single ticker gets weight 1.0."""
        weights = equal_weight_portfolio(["only_asset"])
        assert np.allclose(weights, [1.0])

    def test_ac_fr3900_01_equal_weight_nonzero_input(self):
        """AC-FR3900-01: all weights are strictly positive."""
        tickers = [f"stock_{i}" for i in range(10)]
        weights = equal_weight_portfolio(tickers)
        assert all(w > 0 for w in weights)


class TestCompareToBaseline:
    """Tests for compare_to_baseline."""

    @pytest.fixture
    def baseline_fixture(self):
        """50-asset fixture with known properties."""
        n = 50
        tickers = [f"stock_{i:03d}" for i in range(n)]
        np.random.seed(42)
        mu = {t: 0.001 + 0.0002 * (i % 5) for i, t in enumerate(tickers)}
        cov = 0.0001 * np.eye(n)
        cov += 0.00001 * np.ones((n, n))
        w_opt = np.full(n, 1.0 / n)
        return {"tickers": tickers, "mu": mu, "cov": cov, "w_opt": w_opt}

    def test_ac_fr3900_01_return_type(self, baseline_fixture):
        """AC-FR3900-01: compare_to_baseline returns ComparisonReport."""
        result = compare_to_baseline(
            baseline_fixture["w_opt"],
            baseline_fixture["mu"],
            baseline_fixture["cov"],
        )
        assert isinstance(result, ComparisonReport)
        assert isinstance(result.optimized, dict)
        assert isinstance(result.equal_weight, dict)
        assert isinstance(result.delta, dict)

    def test_ac_fr3900_01_keys(self, baseline_fixture):
        """AC-FR3900-01: both optimized and equal_weight dicts have expected keys."""
        result = compare_to_baseline(
            baseline_fixture["w_opt"],
            baseline_fixture["mu"],
            baseline_fixture["cov"],
        )
        expected_keys = {"expected_return", "volatility", "sharpe", "max_weight", "turnover"}
        assert result.optimized.keys() == expected_keys
        assert result.equal_weight.keys() == expected_keys

    def test_ac_fr3900_01_delta_keys(self, baseline_fixture):
        """AC-FR3900-01: delta dict has expected keys."""
        result = compare_to_baseline(
            baseline_fixture["w_opt"],
            baseline_fixture["mu"],
            baseline_fixture["cov"],
        )
        assert result.delta.keys() == {"expected_return", "volatility", "sharpe", "max_weight", "turnover"}

    def test_ac_fr3900_02_turnover_first_run(self, baseline_fixture):
        """AC-FR3900-02: first run (w_prev=0) turnover = 0.5."""
        result = compare_to_baseline(
            baseline_fixture["w_opt"],
            baseline_fixture["mu"],
            baseline_fixture["cov"],
        )
        expected_turnover = 0.5 * np.sum(np.abs(baseline_fixture["w_opt"]))
        assert np.isclose(result.optimized["turnover"], expected_turnover, atol=1e-6)
        assert np.isclose(result.optimized["turnover"], 0.5, atol=1e-6)

    def test_ac_fr3900_02_turnover_with_prev(self, baseline_fixture):
        """AC-FR3900-02: turnover = 0.5 * sum(|w_opt - w_prev|) when w_prev is provided."""
        w_prev = np.zeros(50)
        result = compare_to_baseline(
            baseline_fixture["w_opt"],
            baseline_fixture["mu"],
            baseline_fixture["cov"],
            w_prev=w_prev,
        )
        expected = 0.5 * np.sum(np.abs(baseline_fixture["w_opt"] - w_prev))
        assert np.isclose(result.optimized["turnover"], expected, atol=1e-6)

    def test_ac_fr3900_03_optimized_sharpe_lower_than_baseline(self):
        """AC-FR3900-03: optimized sharpe < baseline → WARNING log, not error."""
        import io
        from loguru import logger as loguru_logger

        n = 10
        tickers = [f"s{i}" for i in range(n)]
        # Make optimized portfolio have terrible sharpe vs equal weight
        mu = {t: 0.001 for t in tickers}
        cov = 0.01 * np.eye(n)
        w_opt = np.array([0.9] + [0.1 / (n - 1)] * (n - 1))  # concentrated = higher risk

        stream = io.StringIO()
        handler_id = loguru_logger.add(stream, level="WARNING", format="{message}")
        try:
            result = compare_to_baseline(w_opt, mu, cov)
        finally:
            loguru_logger.remove(handler_id)

        # WARNING log must be emitted
        log_output = stream.getvalue().lower()
        assert "optimized sharpe < baseline" in log_output or "sharpe" in log_output
        # Process completes without error
        assert isinstance(result, ComparisonReport)

    def test_ac_fr3900_01_sharpe_computed(self, baseline_fixture):
        """AC-FR3900-01: Sharpe ratio is computed for both portfolios."""
        result = compare_to_baseline(
            baseline_fixture["w_opt"],
            baseline_fixture["mu"],
            baseline_fixture["cov"],
        )
        # Sharpe should be finite
        assert np.isfinite(result.optimized["sharpe"])
        assert np.isfinite(result.equal_weight["sharpe"])

    def test_ac_fr3900_01_max_weight(self, baseline_fixture):
        """AC-FR3900-01: max_weight is correctly reported."""
        result = compare_to_baseline(
            baseline_fixture["w_opt"],
            baseline_fixture["mu"],
            baseline_fixture["cov"],
        )
        assert result.optimized["max_weight"] == pytest.approx(1.0 / 50, rel=1e-6)
        assert result.equal_weight["max_weight"] == pytest.approx(1.0 / 50, rel=1e-6)
