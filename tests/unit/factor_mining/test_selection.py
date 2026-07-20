"""Unit tests for factor selection — Top-K + Pearson deduplication (FR-0400)."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from trader_off.factor_mining.evaluation import FactorEvaluation
from trader_off.factor_mining.expression import FactorSpec

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_ic_ts(
    n_days: int = 30,
    values: list[float] | None = None,
    start_date: date | None = None,
    seed: int = 42,
) -> pl.DataFrame:
    """Create a synthetic IC time series DataFrame.

    Args:
        n_days: Number of trading days.
        values: Optional explicit IC values. If None, generates random values.
        start_date: Start date, defaults to 2024-01-01.
        seed: Random seed for generated values. Use different seeds for
            different factors to avoid spurious correlations.

    Returns:
        DataFrame with columns ``date``, ``ic``.
    """
    if start_date is None:
        start_date = date(2024, 1, 1)
    dates = [start_date + timedelta(days=i) for i in range(n_days)]
    if values is None:
        rng = np.random.RandomState(seed)
        values = list(rng.randn(n_days).astype(float))
    else:
        # Pad or truncate to n_days
        if len(values) < n_days:
            values = values + [0.0] * (n_days - len(values))
        elif len(values) > n_days:
            values = values[:n_days]
    return pl.DataFrame(
        {"date": dates, "ic": values},
        schema={"date": pl.Date, "ic": pl.Float64},
    )


def _make_ic_ts_correlated(
    n_days: int = 30,
    correlation: float = 0.98,
    seed: int = 42,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Create two IC time series with a given Pearson correlation.

    Uses a bivariate normal generation: ic_2 = corr * ic_1 + sqrt(1-corr^2) * noise.
    """
    rng = np.random.RandomState(seed)
    x = rng.randn(n_days)
    noise = rng.randn(n_days)
    y = correlation * x + np.sqrt(max(1 - correlation**2, 0)) * noise
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n_days)]
    ic1 = pl.DataFrame(
        {"date": dates, "ic": list(x.astype(float))},
        schema={"date": pl.Date, "ic": pl.Float64},
    )
    ic2 = pl.DataFrame(
        {"date": dates, "ic": list(y.astype(float))},
        schema={"date": pl.Date, "ic": pl.Float64},
    )
    return ic1, ic2


def _make_ic_ts_pair_correlated(
    n_days: int = 30,
    correlation: float = 0.98,
    seed: int = 42,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Alias for _make_ic_ts_correlated."""
    return _make_ic_ts_correlated(n_days, correlation, seed)


def _make_eval(
    icir: float,
    ic_ts: pl.DataFrame | None = None,
    n_days: int = 30,
    ic_mean: float | None = None,
    ic_std: float | None = None,
) -> FactorEvaluation:
    """Create a FactorEvaluation with controlled icir and optional ic_ts.

    Args:
        icir: The ICIR value for this evaluation.
        ic_ts: Optional IC time series. If None, generates a random one.
        n_days: Number of days for auto-generated ic_ts.
        ic_mean: Explicit ic_mean. Defaults to icir if ic_std=1, else derived.
        ic_std: Explicit ic_std. Defaults to 1.0.
    """
    if ic_std is None:
        ic_std = 1.0
    if ic_mean is None:
        ic_mean = icir * ic_std

    if ic_ts is None:
        ic_ts = _make_ic_ts(n_days)

    empty_rank = pl.DataFrame(
        schema={"date": pl.Date, "rank_ic": pl.Float64},
    )
    empty_layered = pl.DataFrame(
        {"layer": list(range(1, 6)), "mean_return": [0.0] * 5},
        schema={"layer": pl.Int32, "mean_return": pl.Float64},
    )
    return FactorEvaluation(
        ic_ts=ic_ts,
        rank_ic_ts=empty_rank,
        ic_mean=ic_mean,
        ic_std=ic_std,
        icir=icir,
        rank_ic_mean=0.0,
        rank_ic_std=0.0,
        layered_returns=empty_layered,
    )


def _make_spec(
    factor_id: str,
    category: str = "momentum",
) -> FactorSpec:
    """Create a minimal FactorSpec for testing."""
    return FactorSpec(
        id=factor_id,
        template_name="test_template",
        category=category,  # type: ignore[arg-type]
        formula="test_formula",
        compute_fn=lambda df: pl.Series("factor", [0.0], dtype=pl.Float64),
        params={},
    )


def _make_evals_and_specs(
    icirs: list[float],
    seed: int = 42,
) -> tuple[list[FactorEvaluation], list[FactorSpec]]:
    """Create paired evaluations and specs with given icir values.

    Each evaluation gets a unique random ic_ts (uncorrelated by default).
    """
    evaluations = []
    specs = []
    for i, icir in enumerate(icirs):
        ev_ic_ts = _make_ic_ts(30, start_date=date(2024, 1, 1), values=None)
        # Use different seed for each
        rng = np.random.RandomState(seed + i)
        vals = list(rng.randn(30).astype(float))
        ev_ic_ts = _make_ic_ts(30, values=vals)
        evaluations.append(_make_eval(icir, ic_ts=ev_ic_ts))
        specs.append(_make_spec(f"factor_{i:03d}"))
    return evaluations, specs


# ---------------------------------------------------------------------------
# AC-FR0400-01: Top-K sort by ICIR descending, no redundancy removal
# ---------------------------------------------------------------------------


class TestACFR040001TopKDescending:
    """AC-FR0400-01: select_factors returns top_k factors sorted by icir desc."""

    def test_ac_fr0400_01_all_30_returned_sorted_by_icir(self):
        """AC-FR0400-01: 30 evaluations, top_k=30, corr_threshold=0.9
        → returns 30 factors sorted by icir descending, no redundancy removal."""
        from trader_off.factor_mining.selection import (
            select_factors,
        )

        # Create 30 evals with icir 0.9 down to 0.1, shuffled
        icirs = [round(0.9 - i * 0.025, 4) for i in range(30)]
        rng = np.random.RandomState(42)
        shuffled_indices = list(range(30))
        rng.shuffle(shuffled_indices)
        shuffled_icirs = [icirs[i] for i in shuffled_indices]

        evaluations = []
        specs = []
        for rank, icir in enumerate(shuffled_icirs):
            ic_ts = _make_ic_ts(30, start_date=date(2024, 1, 1), seed=1000 + rank)
            evaluations.append(_make_eval(icir, ic_ts=ic_ts))
            specs.append(_make_spec(f"factor_{shuffled_indices[rank]:03d}"))

        selected, diag = select_factors(evaluations, specs, top_k=30, corr_threshold=0.9)

        assert len(selected) == 30
        assert diag.final_k == 30
        assert diag.top_k_requested == 30
        assert diag.removed_by_redundancy == []

        # Verify descending icir order
        selected_icirs = [evaluations[specs.index(s)].icir for s in selected]
        for i in range(29):
            assert selected_icirs[i] >= selected_icirs[i + 1], (
                f"ICIR not descending at index {i}: {selected_icirs[i]} < {selected_icirs[i + 1]}"
            )

    def test_ac_fr0400_01_icir_tie_lexicographic_order(self):
        """AC-FR0400-01: When icir values are equal, factors sort by id ascending."""
        from trader_off.factor_mining.selection import select_factors

        evaluations = [
            _make_eval(0.5, ic_ts=_make_ic_ts(30, seed=10)),
            _make_eval(0.5, ic_ts=_make_ic_ts(30, seed=20)),
            _make_eval(0.5, ic_ts=_make_ic_ts(30, seed=30)),
        ]
        specs = [
            _make_spec("c_factor"),
            _make_spec("a_factor"),
            _make_spec("b_factor"),
        ]

        selected, _ = select_factors(evaluations, specs, top_k=3, corr_threshold=0.9)

        assert len(selected) == 3
        # Sorted by icir desc, then id asc (tiebreaker)
        assert selected[0].id == "a_factor"
        assert selected[1].id == "b_factor"
        assert selected[2].id == "c_factor"


# ---------------------------------------------------------------------------
# AC-FR0400-02: Pearson redundancy removal
# ---------------------------------------------------------------------------


class TestACFR040002RedundancyRemoval:
    """AC-FR0400-02: Redundant factors (|Pearson| > threshold) are removed."""

    def test_ac_fr0400_02_five_redundant_pairs_removed(self):
        """AC-FR0400-02: 50 factors, 5 redundant pairs (Pearson > 0.95),
        top_k=30, corr_threshold=0.9 → 25 selected, 5 removed.
        """
        from trader_off.factor_mining.selection import (
            SelectionDiagnostics,
            select_factors,
        )

        # Strategy: create 50 factors, icir descending from 1.0 to 0.02.
        # For 5 pairs, make their IC time series highly correlated (Pearson ≈ 0.98).
        # The pair members have consecutive positions (e.g., positions 10-11, 14-15, ...)
        # so the lower-icir one gets removed.
        n_total = 50

        # ICIR values: descending from 1.0
        icirs = [round(1.0 - i * 0.02, 4) for i in range(n_total)]

        # Choose 5 disjoint pairs within the top 30 (indices 0-29)
        # Each pair: (higher_icir_idx, lower_icir_idx) consecutive
        pair_indices = [(8, 9), (13, 14), (18, 19), (23, 24), (28, 29)]

        evaluations = []
        specs = []
        ic_ts_cache: dict[int, pl.DataFrame] = {}

        for i in range(n_total):
            spec_id = f"factor_{i:03d}"
            # Check if this index is part of a redundant pair
            is_primary = any(i == p[0] for p in pair_indices)
            is_secondary = any(i == p[1] for p in pair_indices)

            if is_primary:
                # Generate a base IC series
                rng = np.random.RandomState(1000 + i)
                base = list(rng.randn(60).astype(float))
                ic_ts_i = _make_ic_ts(60, values=base)
                ic_ts_cache[i] = ic_ts_i
            elif is_secondary:
                # Find the corresponding primary
                pair_primary = next(p[0] for p in pair_indices if p[1] == i)
                primary_ic = ic_ts_cache[pair_primary]["ic"].to_numpy()
                # Create highly correlated series (Pearson > 0.95)
                rng = np.random.RandomState(2000 + i)
                noise = rng.randn(60) * 0.1
                correlated = primary_ic * 0.98 + noise
                ic_ts_i = pl.DataFrame(
                    {
                        "date": ic_ts_cache[pair_primary]["date"],
                        "ic": list(correlated.astype(float)),
                    },
                    schema={"date": pl.Date, "ic": pl.Float64},
                )
            else:
                rng = np.random.RandomState(3000 + i)
                vals = list(rng.randn(60).astype(float))
                ic_ts_i = _make_ic_ts(60, values=vals)

            evaluations.append(_make_eval(icirs[i], ic_ts=ic_ts_i))
            specs.append(_make_spec(spec_id))

        selected, diag = select_factors(evaluations, specs, top_k=30, corr_threshold=0.9)

        assert len(selected) == 25, f"Expected 25 selected, got {len(selected)}"
        assert diag.final_k == 25
        assert diag.top_k_requested == 30
        assert len(diag.removed_by_redundancy) == 5, (
            f"Expected 5 removed, got {len(diag.removed_by_redundancy)}: "
            f"{diag.removed_by_redundancy}"
        )
        assert isinstance(diag, SelectionDiagnostics)

        # Verify removed factors are the secondary ones (lower icir of each pair)
        for _, secondary_idx in pair_indices:
            removed_id = f"factor_{secondary_idx:03d}"
            assert removed_id in diag.removed_by_redundancy, (
                f"Expected {removed_id} in removed list"
            )

        # Verify selected factors are sorted by icir descending
        # Build (spec_id → icir) mapping
        spec_to_icir = {s.id: evaluations[i].icir for i, s in enumerate(specs)}
        for i in range(len(selected) - 1):
            assert spec_to_icir[selected[i].id] >= spec_to_icir[selected[i + 1].id], (
                f"ICIR not descending at position {i}"
            )

    def test_ac_fr0400_02_higher_icir_kept_when_redundant(self):
        """AC-FR0400-02: In a redundant pair, the factor with higher icir is kept."""
        from trader_off.factor_mining.selection import select_factors

        # Create two factors with correlated IC series
        ic1, ic2 = _make_ic_ts_pair_correlated(30, correlation=0.98)

        ev_high = _make_eval(0.8, ic_ts=ic1)
        ev_low = _make_eval(0.5, ic_ts=ic2)
        evaluations = [ev_high, ev_low]
        specs = [_make_spec("high_icir"), _make_spec("low_icir")]

        selected, diag = select_factors(evaluations, specs, top_k=2, corr_threshold=0.9)

        # The higher-icir factor should be kept, lower removed
        assert len(selected) == 1
        assert selected[0].id == "high_icir"
        assert "low_icir" in diag.removed_by_redundancy

    def test_ac_fr0400_02_no_removal_below_threshold(self):
        """AC-FR0400-02: Factors below correlation threshold are not removed."""
        from trader_off.factor_mining.selection import select_factors

        # Two factors with moderate correlation (0.5), threshold 0.9 → both kept
        ic1, ic2 = _make_ic_ts_pair_correlated(30, correlation=0.5)

        ev1 = _make_eval(0.8, ic_ts=ic1)
        ev2 = _make_eval(0.7, ic_ts=ic2)
        evaluations = [ev1, ev2]
        specs = [_make_spec("factor_a"), _make_spec("factor_b")]

        selected, diag = select_factors(evaluations, specs, top_k=2, corr_threshold=0.9)

        assert len(selected) == 2
        assert diag.removed_by_redundancy == []


# ---------------------------------------------------------------------------
# AC-FR0400-03: Candidates fewer than top_k → all kept + WARNING
# ---------------------------------------------------------------------------


class TestACFR040003FewerThanTopK:
    """AC-FR0400-03: When candidates < top_k, all are kept with a WARNING."""

    def test_ac_fr0400_03_fewer_than_top_k_all_kept(self):
        """AC-FR0400-03: 8 candidates, top_k=30 → all 8 returned."""
        from trader_off.factor_mining.selection import select_factors

        icirs = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
        evaluations = []
        specs = []
        for i, icir in enumerate(icirs):
            ic_ts = _make_ic_ts(30, start_date=date(2024, 1, 1), seed=2000 + i)
            evaluations.append(_make_eval(icir, ic_ts=ic_ts))
            specs.append(_make_spec(f"factor_{i:02d}"))

        selected, diag = select_factors(evaluations, specs, top_k=30, corr_threshold=0.9)

        assert len(selected) == 8
        assert diag.final_k == 8
        assert diag.top_k_requested == 30
        assert diag.removed_by_redundancy == []

    def test_ac_fr0400_03_warning_when_fewer_than_top_k(self, caplog):
        """AC-FR0400-03: WARNING log when selected fewer than top_k."""
        from trader_off.factor_mining.selection import select_factors

        evaluations = [_make_eval(0.5, ic_ts=_make_ic_ts(30))]
        specs = [_make_spec("sole_factor")]

        with caplog.at_level(logging.WARNING, logger="trader_off.factor_mining.selection"):
            select_factors(evaluations, specs, top_k=30, corr_threshold=0.9)

        assert "fewer than top_k" in caplog.text

    def test_ac_fr0400_03_no_warning_when_exact_top_k(self, caplog):
        """AC-FR0400-03: No WARNING when selected count equals top_k."""
        from trader_off.factor_mining.selection import select_factors

        evaluations = []
        specs = []
        for i in range(10):
            ic_ts = _make_ic_ts(30, start_date=date(2024, 1, 1), seed=3000 + i)
            evaluations.append(_make_eval(0.9 - i * 0.08, ic_ts=ic_ts))
            specs.append(_make_spec(f"factor_{i:02d}"))

        with caplog.at_level(logging.WARNING, logger="trader_off.factor_mining.selection"):
            select_factors(evaluations, specs, top_k=10, corr_threshold=0.9)

        assert "fewer than top_k" not in caplog.text


# ---------------------------------------------------------------------------
# AC-FR0400-04: ICIR tiebreaker — lexicographic id ordering
# ---------------------------------------------------------------------------


class TestACFR040004ICIRTiebreaker:
    """AC-FR0400-04: When redundant factors have equal ICIR, keep lexicographically
    smaller id."""

    def test_ac_fr0400_04_keep_smaller_id_on_icir_tie(self):
        """AC-FR0400-04: Two redundant factors with identical icir
        → factor with smaller id (lexicographically) is kept."""
        from trader_off.factor_mining.selection import select_factors

        # Create two factors with correlated IC series and equal icir
        ic1, ic2 = _make_ic_ts_pair_correlated(30, correlation=0.98)

        ev_a = _make_eval(0.6, ic_ts=ic1)
        ev_b = _make_eval(0.6, ic_ts=ic2)
        evaluations = [ev_a, ev_b]
        specs = [_make_spec("alpha_factor"), _make_spec("beta_factor")]

        selected, diag = select_factors(evaluations, specs, top_k=2, corr_threshold=0.9)

        # alpha_factor < beta_factor lexicographically → alpha kept
        assert len(selected) == 1
        assert selected[0].id == "alpha_factor"
        assert "beta_factor" in diag.removed_by_redundancy

    def test_ac_fr0400_04_tiebreak_only_when_redundant(self):
        """AC-FR0400-04: ICIR tiebreaker only applies when factors are redundant."""
        from trader_off.factor_mining.selection import select_factors

        # Two uncorrelated factors with equal icir → both kept
        ic_ts_a = _make_ic_ts(30, start_date=date(2024, 1, 1))
        ic_ts_b = _make_ic_ts(30, start_date=date(2024, 2, 1))

        ev_a = _make_eval(0.5, ic_ts=ic_ts_a)
        ev_b = _make_eval(0.5, ic_ts=ic_ts_b)
        evaluations = [ev_a, ev_b]
        specs = [_make_spec("zeta_factor"), _make_spec("alpha_factor")]

        selected, diag = select_factors(evaluations, specs, top_k=2, corr_threshold=0.9)

        # Both should be selected (uncorrelated), sorted by id asc
        assert len(selected) == 2
        assert selected[0].id == "alpha_factor"
        assert selected[1].id == "zeta_factor"
        assert diag.removed_by_redundancy == []


# ---------------------------------------------------------------------------
# Edge cases for SelectionDiagnostics
# ---------------------------------------------------------------------------


class TestSelectionDiagnostics:
    """Edge cases for SelectionDiagnostics dataclass."""

    def test_selection_diagnostics_fields(self):
        """SelectionDiagnostics has correct fields."""
        from trader_off.factor_mining.selection import SelectionDiagnostics

        diag = SelectionDiagnostics(
            removed_by_redundancy=["f1", "f2"],
            final_k=3,
            top_k_requested=5,
        )

        assert diag.removed_by_redundancy == ["f1", "f2"]
        assert diag.final_k == 3
        assert diag.top_k_requested == 5

    def test_selection_diagnostics_immutable(self):
        """SelectionDiagnostics is frozen (immutable)."""
        from trader_off.factor_mining.selection import SelectionDiagnostics

        diag = SelectionDiagnostics(
            removed_by_redundancy=[],
            final_k=0,
            top_k_requested=30,
        )
        with pytest.raises(Exception):
            diag.final_k = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Edge cases for select_factors
# ---------------------------------------------------------------------------


class TestSelectFactorsEdgeCases:
    """Edge case coverage for select_factors."""

    def test_empty_evaluations(self):
        """Empty evaluations list returns empty result."""
        from trader_off.factor_mining.selection import select_factors

        selected, diag = select_factors([], [], top_k=30, corr_threshold=0.9)
        assert selected == []
        assert diag.final_k == 0
        assert diag.top_k_requested == 30
        assert diag.removed_by_redundancy == []

    def test_single_evaluation(self):
        """Single evaluation returns that single factor."""
        from trader_off.factor_mining.selection import select_factors

        ev = _make_eval(0.5, ic_ts=_make_ic_ts(30))
        spec = _make_spec("sole")
        selected, diag = select_factors([ev], [spec], top_k=30, corr_threshold=0.9)
        assert len(selected) == 1
        assert selected[0].id == "sole"
        assert diag.final_k == 1

    def test_custom_corr_threshold(self):
        """Custom corr_threshold parameter is respected."""
        from trader_off.factor_mining.selection import select_factors

        # Two factors with correlation ~0.5
        ic1, ic2 = _make_ic_ts_pair_correlated(30, correlation=0.5)
        ev1 = _make_eval(0.8, ic_ts=ic1)
        ev2 = _make_eval(0.7, ic_ts=ic2)
        specs = [_make_spec("high"), _make_spec("low")]

        # With threshold 0.4 (strict) → both kept (|corr| might be < 0.4)
        # Actually correlation=0.5, threshold=0.4 → removed
        # threshold=0.6 → both kept
        selected_strict, _ = select_factors([ev1, ev2], specs, top_k=2, corr_threshold=0.6)
        assert len(selected_strict) == 2  # |0.5| < 0.6 → keep both

        # threshold=0.4 → |0.5| >= 0.4 → lower icir removed
        selected_loose, diag_loose = select_factors([ev1, ev2], specs, top_k=2, corr_threshold=0.4)
        assert len(selected_loose) == 1
        assert selected_loose[0].id == "high"
        assert "low" in diag_loose.removed_by_redundancy

    def test_ic_ts_mismatched_dates(self):
        """Factors with non-overlapping IC dates are not considered redundant."""
        from trader_off.factor_mining.selection import select_factors

        ic1 = _make_ic_ts(30, start_date=date(2024, 1, 1))
        ic2 = _make_ic_ts(30, start_date=date(2025, 1, 1))

        ev1 = _make_eval(0.8, ic_ts=ic1)
        ev2 = _make_eval(0.7, ic_ts=ic2)
        specs = [_make_spec("high"), _make_spec("low")]

        selected, diag = select_factors([ev1, ev2], specs, top_k=2, corr_threshold=0.1)

        # Non-overlapping dates → cannot compute correlation → not redundant
        assert len(selected) == 2
        assert diag.removed_by_redundancy == []

    def test_ic_ts_empty(self):
        """Factor with empty IC time series is handled gracefully."""
        from trader_off.factor_mining.selection import select_factors

        empty_ic = pl.DataFrame(
            schema={"date": pl.Date, "ic": pl.Float64},
        )
        ev1 = _make_eval(0.8, ic_ts=empty_ic)
        ev2 = _make_eval(0.7, ic_ts=_make_ic_ts(30))
        specs = [_make_spec("empty_ic"), _make_spec("normal")]

        selected, diag = select_factors([ev1, ev2], specs, top_k=2, corr_threshold=0.1)

        # Empty IC → cannot compute correlation → not redundant
        assert len(selected) == 2

    def test_mismatched_eval_spec_lengths(self):
        """ValueError when evaluations and factor_specs have different lengths."""
        from trader_off.factor_mining.selection import select_factors

        ev = _make_eval(0.5, ic_ts=_make_ic_ts(30))
        spec = _make_spec("sole")

        with pytest.raises(ValueError, match="must have the same length"):
            select_factors([ev, ev], [spec], top_k=30)

    def test_constant_ic_ts_handled(self):
        """Factors with constant IC time series (std=0) are handled gracefully."""
        from trader_off.factor_mining.selection import select_factors

        # Create two factors with constant IC values
        const_ic = pl.DataFrame(
            {"date": [date(2024, 1, 1) + timedelta(days=i) for i in range(10)], "ic": [1.0] * 10},
            schema={"date": pl.Date, "ic": pl.Float64},
        )
        ev1 = _make_eval(0.8, ic_ts=const_ic)
        ev2 = _make_eval(0.7, ic_ts=_make_ic_ts(30))
        specs = [_make_spec("const_ic"), _make_spec("normal")]

        selected, diag = select_factors([ev1, ev2], specs, top_k=2, corr_threshold=0.1)

        # Constant IC → std=0 → cannot compute correlation → not redundant
        assert len(selected) == 2
