"""Unit tests for factor evaluation — IC / ICIR / Rank IC (FR-0300)."""

import inspect
import logging
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


def _make_factor_and_labels(
    n_assets: int = 50,
    n_days: int = 100,
    seed: int = 42,
) -> tuple[pl.DataFrame, pl.DataFrame, list[date]]:
    """Generate synthetic factor values and labels for testing.

    Args:
        n_assets: Number of unique assets.
        n_days: Number of trading days.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (factor_values, labels, dates).
    """
    rng = np.random.RandomState(seed)
    start = date(2024, 1, 1)
    dates = [start + timedelta(days=i) for i in range(n_days)]

    fv_rows: list[dict] = []
    lb_rows: list[dict] = []
    for d in dates:
        for a in range(n_assets):
            asset = f"{a:04d}.SZ"
            value = rng.randn()
            label = value * 0.3 + rng.randn() * 0.1
            fv_rows.append({"asset": asset, "date": d, "value": float(value)})
            lb_rows.append({"asset": asset, "date": d, "label": float(label)})

    factor_values = pl.DataFrame(
        fv_rows,
        schema={"asset": pl.Utf8, "date": pl.Date, "value": pl.Float64},
    )
    labels = pl.DataFrame(
        lb_rows,
        schema={"asset": pl.Utf8, "date": pl.Date, "label": pl.Float64},
    )
    return factor_values, labels, dates


def _make_perfectly_correlated(
    n_assets: int = 50,
    n_days: int = 100,
    positive: bool = True,
) -> tuple[pl.DataFrame, pl.DataFrame, list[date]]:
    """Generate factor values perfectly correlated (or anticorrelated) with labels.

    Factor values and labels are linearly related: label = factor_value * sign.
    """
    rng = np.random.RandomState(42)
    start = date(2024, 1, 1)
    dates = [start + timedelta(days=i) for i in range(n_days)]
    sign = 1.0 if positive else -1.0

    fv_rows: list[dict] = []
    lb_rows: list[dict] = []
    for d in dates:
        for a in range(n_assets):
            asset = f"{a:04d}.SZ"
            value = rng.randn()
            label = value * sign  # perfect linear relationship
            fv_rows.append({"asset": asset, "date": d, "value": float(value)})
            lb_rows.append({"asset": asset, "date": d, "label": float(label)})

    factor_values = pl.DataFrame(
        fv_rows,
        schema={"asset": pl.Utf8, "date": pl.Date, "value": pl.Float64},
    )
    labels = pl.DataFrame(
        lb_rows,
        schema={"asset": pl.Utf8, "date": pl.Date, "label": pl.Float64},
    )
    return factor_values, labels, dates


def _make_constant_factor(
    n_assets: int = 50,
    n_days: int = 100,
) -> tuple[pl.DataFrame, pl.DataFrame, list[date]]:
    """Generate factor values that are all constant (std=0) on each date."""
    rng = np.random.RandomState(42)
    start = date(2024, 1, 1)
    dates = [start + timedelta(days=i) for i in range(n_days)]

    fv_rows: list[dict] = []
    lb_rows: list[dict] = []
    for d in dates:
        for a in range(n_assets):
            asset = f"{a:04d}.SZ"
            value = 5.0  # constant across all assets on this date
            label = rng.randn()
            fv_rows.append({"asset": asset, "date": d, "value": value})
            lb_rows.append({"asset": asset, "date": d, "label": float(label)})

    factor_values = pl.DataFrame(
        fv_rows,
        schema={"asset": pl.Utf8, "date": pl.Date, "value": pl.Float64},
    )
    labels = pl.DataFrame(
        lb_rows,
        schema={"asset": pl.Utf8, "date": pl.Date, "label": pl.Float64},
    )
    return factor_values, labels, dates


# ---------------------------------------------------------------------------
# AC-FR0300-01: FactorEvaluation structure validation
# ---------------------------------------------------------------------------


class TestACFR030001EvaluationStructure:
    """AC-FR0300-01: evaluate_factor returns FactorEvaluation with correct fields."""

    def test_ac_fr0300_01_returns_factor_evaluation(self):
        """AC-FR0300-01: evaluate_factor returns FactorEvaluation dataclass
        with ic_ts, rank_ic_ts, ic_mean, ic_std, icir, rank_ic_mean, rank_ic_std,
        layered_returns (5 rows, columns layer/mean_return)."""
        from trader_off.factor_mining.evaluation import FactorEvaluation, evaluate_factor

        factor_values, labels, dates = _make_factor_and_labels()

        result = evaluate_factor(factor_values, labels, dates)

        assert isinstance(result, FactorEvaluation)
        # ic_ts: columns date/ic
        assert isinstance(result.ic_ts, pl.DataFrame)
        assert set(result.ic_ts.columns) == {"date", "ic"}
        # rank_ic_ts: columns date/rank_ic
        assert isinstance(result.rank_ic_ts, pl.DataFrame)
        assert set(result.rank_ic_ts.columns) == {"date", "rank_ic"}
        # scalar fields
        assert isinstance(result.ic_mean, float)
        assert isinstance(result.ic_std, float)
        assert isinstance(result.icir, float)
        assert isinstance(result.rank_ic_mean, float)
        assert isinstance(result.rank_ic_std, float)
        # layered_returns: 5 rows, columns layer/mean_return
        assert isinstance(result.layered_returns, pl.DataFrame)
        assert len(result.layered_returns) == 5
        assert set(result.layered_returns.columns) == {"layer", "mean_return"}

    def test_ac_fr0300_01_ic_ts_row_count(self):
        """AC-FR0300-01: ic_ts has one row per evaluated date."""
        from trader_off.factor_mining.evaluation import evaluate_factor

        factor_values, labels, dates = _make_factor_and_labels(n_assets=30, n_days=10)
        result = evaluate_factor(factor_values, labels, dates)

        assert len(result.ic_ts) == 10
        assert len(result.rank_ic_ts) == 10


# ---------------------------------------------------------------------------
# AC-FR0300-02: Perfect positive correlation → ic_mean ≈ 1.0, rank_ic_mean ≈ 1.0
# ---------------------------------------------------------------------------


class TestACFR030002PerfectPositive:
    """AC-FR0300-02: Perfect positive correlation → ic_mean ≈ 1.0."""

    def test_ac_fr0300_02_perfect_positive_ic(self):
        """AC-FR0300-02: When factor and label are perfectly positively correlated,
        ic_mean ≈ 1.0, rank_ic_mean ≈ 1.0 (tolerance < 0.01)."""
        from trader_off.factor_mining.evaluation import evaluate_factor

        factor_values, labels, dates = _make_perfectly_correlated(positive=True)

        result = evaluate_factor(factor_values, labels, dates)

        assert abs(result.ic_mean - 1.0) < 0.01, f"ic_mean={result.ic_mean}"
        assert abs(result.rank_ic_mean - 1.0) < 0.01, f"rank_ic_mean={result.rank_ic_mean}"


# ---------------------------------------------------------------------------
# AC-FR0300-03: Perfect negative correlation → ic_mean ≈ -1.0
# ---------------------------------------------------------------------------


class TestACFR030003PerfectNegative:
    """AC-FR0300-03: Perfect negative correlation → ic_mean ≈ -1.0."""

    def test_ac_fr0300_03_perfect_negative_ic(self):
        """AC-FR0300-03: When factor and label are perfectly negatively correlated,
        ic_mean ≈ -1.0 (tolerance < 0.01)."""
        from trader_off.factor_mining.evaluation import evaluate_factor

        factor_values, labels, dates = _make_perfectly_correlated(positive=False)

        result = evaluate_factor(factor_values, labels, dates)

        assert abs(result.ic_mean - (-1.0)) < 0.01, f"ic_mean={result.ic_mean}"


# ---------------------------------------------------------------------------
# AC-FR0300-04: Zero std factor → icir = 0.0 + WARNING log
# ---------------------------------------------------------------------------


class TestACFR030004ZeroStd:
    """AC-FR0300-04: Constant factor values → icir = 0.0, WARNING log."""

    def test_ac_fr0300_04_constant_factor_icir_zero(self):
        """AC-FR0300-04: When factor values are constant (std=0),
        icir = 0.0."""
        from trader_off.factor_mining.evaluation import evaluate_factor

        factor_values, labels, dates = _make_constant_factor()
        result = evaluate_factor(factor_values, labels, dates)
        assert result.icir == 0.0, f"Expected icir=0.0, got {result.icir}"

    def test_ac_fr0300_04_zero_std_caplog(self, caplog):
        """AC-FR0300-04: WARNING log via caplog with 'zero std' message."""
        from trader_off.factor_mining.evaluation import evaluate_factor

        factor_values, labels, dates = _make_constant_factor()

        with caplog.at_level(logging.WARNING, logger="trader_off.factor_mining.evaluation"):
            evaluate_factor(factor_values, labels, dates)

        assert "zero std" in caplog.text


# ---------------------------------------------------------------------------
# AC-FR0300-05: Reuse v0.1.0 evaluation.ic functions
# ---------------------------------------------------------------------------


class TestACFR030005ReuseV010:
    """AC-FR0300-05: evaluate_factor reuses v0.1.0 evaluation.ic functions."""

    def test_ac_fr0300_05_functions_importable_from_v010(self):
        """AC-FR0300-05: ic_pearson, ic_spearman, compute_layered_returns
        are importable from trader_off.evaluation.ic without reimplementation."""
        from trader_off.evaluation.ic import (
            compute_layered_returns,
            ic_pearson,
            ic_spearman,
        )

        # All three must be callable
        assert callable(ic_pearson)
        assert callable(ic_spearman)
        assert callable(compute_layered_returns)

    def test_ac_fr0300_05_no_duplicate_implementation(self):
        """AC-FR0300-05: evaluate_factor module does not contain its own
        IC math implementation — it imports from evaluation.ic."""
        import ast
        from pathlib import Path

        eval_path = (
            Path(__file__).parents[3] / "src" / "trader_off" / "factor_mining" / "evaluation.py"
        )
        source = eval_path.read_text()

        # Must import from trader_off.evaluation.ic
        assert (
            "from trader_off.evaluation.ic import" in source
            or "from trader_off.evaluation.ic import (" in source
        ), "evaluation.py must import from trader_off.evaluation.ic"

        # Must NOT define its own pearsonr/spearmanr/scipy.stats calls
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "scipy" not in alias.name, (
                        f"evaluation.py should not import scipy directly, got {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module and "scipy" in node.module:
                    pytest.fail(
                        f"evaluation.py should not import scipy directly, got {node.module}"
                    )

    def test_ac_fr0300_05_source_file_same(self):
        """AC-FR0300-05: ic_pearson and ic_spearman reside in the same
        v0.1.0 source file as expected."""
        from trader_off.evaluation.ic import ic_pearson, ic_spearman

        pearson_file = inspect.getsourcefile(ic_pearson)
        spearman_file = inspect.getsourcefile(ic_spearman)

        assert pearson_file == spearman_file, (
            "ic_pearson and ic_spearman must be from the same source file"
        )
        assert "evaluation/ic.py" in str(pearson_file), (
            f"Expected evaluation/ic.py, got {pearson_file}"
        )


# ---------------------------------------------------------------------------
# Edge case tests for coverage
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case coverage for evaluate_factor."""

    def test_missing_columns_raises_value_error(self):
        """Missing required columns in factor_values raises ValueError."""
        from trader_off.factor_mining.evaluation import evaluate_factor

        bad_fv = pl.DataFrame(
            {"asset": ["A"], "date": [date(2024, 1, 1)]},
            schema={"asset": pl.Utf8, "date": pl.Date},
        )
        labels = pl.DataFrame(
            {"asset": ["A"], "date": [date(2024, 1, 1)], "label": [0.01]},
            schema={"asset": pl.Utf8, "date": pl.Date, "label": pl.Float64},
        )
        with pytest.raises(ValueError, match="factor_values is missing required columns"):
            evaluate_factor(bad_fv, labels, [date(2024, 1, 1)])

    def test_missing_label_columns_raises_value_error(self):
        """Missing required columns in labels raises ValueError."""
        from trader_off.factor_mining.evaluation import evaluate_factor

        fv = pl.DataFrame(
            {"asset": ["A"], "date": [date(2024, 1, 1)], "value": [1.0]},
            schema={"asset": pl.Utf8, "date": pl.Date, "value": pl.Float64},
        )
        bad_labels = pl.DataFrame(
            {"asset": ["A"], "date": [date(2024, 1, 1)]},
            schema={"asset": pl.Utf8, "date": pl.Date},
        )
        with pytest.raises(ValueError, match="labels is missing required columns"):
            evaluate_factor(fv, bad_labels, [date(2024, 1, 1)])

    def test_no_overlapping_data_returns_empty(self):
        """When factor_values and labels have no overlapping (asset, date),
        returns empty FactorEvaluation with zero fields."""
        from trader_off.factor_mining.evaluation import evaluate_factor

        fv = pl.DataFrame(
            {"asset": ["A"], "date": [date(2024, 1, 1)], "value": [1.0]},
            schema={"asset": pl.Utf8, "date": pl.Date, "value": pl.Float64},
        )
        labels = pl.DataFrame(
            {"asset": ["B"], "date": [date(2024, 1, 2)], "label": [0.01]},
            schema={"asset": pl.Utf8, "date": pl.Date, "label": pl.Float64},
        )
        result = evaluate_factor(fv, labels, [date(2024, 1, 1)])
        assert result.ic_mean == 0.0
        assert result.ic_std == 0.0
        assert result.icir == 0.0
        assert len(result.ic_ts) == 0
        assert len(result.rank_ic_ts) == 0
        assert len(result.layered_returns) == 5

    def test_some_dates_missing_from_data(self):
        """Dates not present in merged data are silently skipped."""
        from trader_off.factor_mining.evaluation import evaluate_factor

        fv = pl.DataFrame(
            {"asset": ["A"], "date": [date(2024, 1, 1)], "value": [1.0]},
            schema={"asset": pl.Utf8, "date": pl.Date, "value": pl.Float64},
        )
        labels = pl.DataFrame(
            {"asset": ["A"], "date": [date(2024, 1, 1)], "label": [0.01]},
            schema={"asset": pl.Utf8, "date": pl.Date, "label": pl.Float64},
        )
        # Request evaluation on dates that don't exist in data
        result = evaluate_factor(fv, labels, [date(2025, 1, 1), date(2025, 1, 2)])
        # No matching dates → empty result
        assert len(result.ic_ts) == 0
