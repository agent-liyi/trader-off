"""Unit tests for factor scoring — compute_factor_score (FR-0900).

Covers:
    AC-FR0900-01: compute_factor_score produces correct shape and is consumable
        by v0.1.0 training's expected feature format.
    AC-FR0900-02: output column names match selected factor IDs.
    AC-FR0900-03: (out of scope — default 15 features when no --factor-registry).
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ohlcv_data() -> pl.DataFrame:
    """Small OHLCV fixture: 2 assets × 10 days."""
    import datetime as _dt

    assets = ["000001.SZ", "000002.SZ"]
    raw_dates = [
        _dt.date(2026, 1, 5),
        _dt.date(2026, 1, 6),
        _dt.date(2026, 1, 7),
        _dt.date(2026, 1, 8),
        _dt.date(2026, 1, 9),
        _dt.date(2026, 1, 12),
        _dt.date(2026, 1, 13),
        _dt.date(2026, 1, 14),
        _dt.date(2026, 1, 15),
        _dt.date(2026, 1, 16),
    ]
    np.random.seed(42)
    n_periods = len(raw_dates)
    rows_dict: dict[str, list] = {
        "asset": [],
        "date": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    }
    for asset in assets:
        base_close = 10.0 if asset == "000001.SZ" else 50.0
        for i in range(n_periods):
            rows_dict["asset"].append(asset)
            rows_dict["date"].append(raw_dates[i])
            rows_dict["open"].append(base_close + i * 0.1 + np.random.randn() * 0.05)
            rows_dict["high"].append(base_close + i * 0.15 + abs(np.random.randn()) * 0.1)
            rows_dict["low"].append(base_close + i * 0.05 - abs(np.random.randn()) * 0.1)
            rows_dict["close"].append(base_close + i * 0.1 + np.random.randn() * 0.05)
            rows_dict["volume"].append(1e6 + i * 1e5 + np.random.randn() * 1e4)

    return pl.DataFrame(
        {
            "asset": pl.Series("asset", rows_dict["asset"], dtype=pl.Utf8),
            "date": pl.Series("date", rows_dict["date"], dtype=pl.Date),
            "open": pl.Series("open", rows_dict["open"], dtype=pl.Float64),
            "high": pl.Series("high", rows_dict["high"], dtype=pl.Float64),
            "low": pl.Series("low", rows_dict["low"], dtype=pl.Float64),
            "close": pl.Series("close", rows_dict["close"], dtype=pl.Float64),
            "volume": pl.Series("volume", rows_dict["volume"], dtype=pl.Float64),
        }
    )


@pytest.fixture
def momentum_spec():
    """A single momentum_N_5 FactorSpec."""
    from trader_off.factor_mining.expression import enumerate_factors
    from trader_off.factor_mining.templates import FactorTemplate, IntRangeParam

    t = FactorTemplate(
        name="momentum_N",
        category="momentum",
        fields=["close"],
        params={"N": IntRangeParam(name="N", min=5, max=5, step=5)},
        formula="close[t]/close[t-{N}]-1",
    )
    return enumerate_factors([t], {"N": [5]})[0]


@pytest.fixture
def three_momentum_specs():
    """Three momentum FactorSpecs with N=5,10,20."""
    from trader_off.factor_mining.expression import enumerate_factors
    from trader_off.factor_mining.templates import FactorTemplate, IntRangeParam

    t = FactorTemplate(
        name="momentum_N",
        category="momentum",
        fields=["close"],
        params={"N": IntRangeParam(name="N", min=5, max=20, step=5)},
        formula="close[t]/close[t-{N}]-1",
    )
    return enumerate_factors([t], {"N": [5, 10, 20]})


@pytest.fixture
def multi_template_specs():
    """Mix of momentum and volatility specs for cross-category testing."""
    from trader_off.factor_mining.expression import enumerate_factors
    from trader_off.factor_mining.templates import (
        list_templates,
    )

    # Use only momentum and vol templates with small param space
    templates = [t for t in list_templates() if t.name in ("momentum_N", "vol_N")]
    return enumerate_factors(templates, {"N": [5, 20]})


# ---------------------------------------------------------------------------
# AC-FR0900-01: compute_factor_score shape and trainer consumability
# ---------------------------------------------------------------------------


class TestComputeFactorScoreShapeAndCompatibility:
    """AC-FR0900-01: compute_factor_score produces output with correct shape
    and dtypes, consumable by v0.1.0 training pipeline.
    """

    def test_ac_fr0900_01_output_shape_single_spec(self, ohlcv_data, momentum_spec):
        """AC-FR0900-01: Single spec → one column, same row count as input."""
        from trader_off.factor_mining.score import compute_factor_score

        result = compute_factor_score([momentum_spec], ohlcv_data)

        assert isinstance(result, pl.DataFrame), f"Expected pl.DataFrame, got {type(result)}"
        assert result.height == ohlcv_data.height, (
            f"Row count mismatch: {result.height} vs {ohlcv_data.height}"
        )
        assert result.width == 1, f"Expected 1 column, got {result.width}"

    def test_ac_fr0900_01_output_shape_three_specs(self, ohlcv_data, three_momentum_specs):
        """AC-FR0900-01: N specs → N columns, same row count as input."""
        from trader_off.factor_mining.score import compute_factor_score

        result = compute_factor_score(three_momentum_specs, ohlcv_data)

        assert result.height == ohlcv_data.height
        assert result.width == len(three_momentum_specs), (
            f"Expected {len(three_momentum_specs)} columns, got {result.width}"
        )

    def test_ac_fr0900_01_all_columns_float64(self, ohlcv_data, three_momentum_specs):
        """AC-FR0900-01: All output columns are Float64, compatible with numpy."""
        from trader_off.factor_mining.score import compute_factor_score

        result = compute_factor_score(three_momentum_specs, ohlcv_data)

        for col in result.columns:
            assert result[col].dtype == pl.Float64, (
                f"Column {col} has dtype {result[col].dtype}, expected Float64"
            )

    def test_ac_fr0900_01_convertible_to_numpy(self, ohlcv_data, three_momentum_specs):
        """AC-FR0900-01: Output can be converted to numpy (as trainer does)."""
        from trader_off.factor_mining.score import compute_factor_score

        result = compute_factor_score(three_momentum_specs, ohlcv_data)

        # Simulate what trainer does: convert to numpy
        arr = result.to_numpy()
        assert isinstance(arr, np.ndarray), f"Expected np.ndarray, got {type(arr)}"
        assert arr.shape == (ohlcv_data.height, len(three_momentum_specs)), (
            f"Shape mismatch: {arr.shape} vs ({ohlcv_data.height}, {len(three_momentum_specs)})"
        )
        assert arr.dtype in (np.float64, np.float32), f"Unexpected dtype: {arr.dtype}"

    def test_ac_fr0900_01_no_inf_values(self, ohlcv_data, multi_template_specs):
        """AC-FR0900-01: Output does not contain inf values for well-formed input."""
        from trader_off.factor_mining.score import compute_factor_score

        result = compute_factor_score(multi_template_specs, ohlcv_data)
        arr = result.to_numpy()
        assert not np.any(np.isinf(arr)), "Output contains inf values"

    def test_ac_fr0900_01_feature_names_count_matches_specs(self, ohlcv_data, multi_template_specs):
        """AC-FR0900-01: len(feature_names) == len(specs), as expected by metadata."""
        from trader_off.factor_mining.score import compute_factor_score

        result = compute_factor_score(multi_template_specs, ohlcv_data)
        feature_names = result.columns

        assert len(feature_names) == len(multi_template_specs), (
            f"feature_names count {len(feature_names)} != specs count {len(multi_template_specs)}"
        )


# ---------------------------------------------------------------------------
# AC-FR0900-02: column names match selected factor IDs
# ---------------------------------------------------------------------------


class TestComputeFactorScoreColumnNaming:
    """AC-FR0900-02: Output column names must match spec IDs so that
    feature_names.json can be populated correctly.
    """

    def test_ac_fr0900_02_columns_match_spec_ids(self, ohlcv_data, three_momentum_specs):
        """AC-FR0900-02: Output column names exactly equal spec IDs."""
        from trader_off.factor_mining.score import compute_factor_score

        result = compute_factor_score(three_momentum_specs, ohlcv_data)
        expected_ids = {s.id for s in three_momentum_specs}
        actual_cols = set(result.columns)

        assert actual_cols == expected_ids, (
            f"Column mismatch: expected {expected_ids}, got {actual_cols}"
        )

    def test_ac_fr0900_02_column_order_matches_spec_order(self, ohlcv_data, three_momentum_specs):
        """AC-FR0900-02: Column ordering follows the order of specs in the list."""
        from trader_off.factor_mining.score import compute_factor_score

        result = compute_factor_score(three_momentum_specs, ohlcv_data)
        expected_order = [s.id for s in three_momentum_specs]

        assert list(result.columns) == expected_order, (
            f"Column order mismatch: expected {expected_order}, got {list(result.columns)}"
        )

    def test_ac_fr0900_02_multi_template_ids_preserved(self, ohlcv_data, multi_template_specs):
        """AC-FR0900-02: All spec IDs are present as columns in multi-template output."""
        from trader_off.factor_mining.score import compute_factor_score

        result = compute_factor_score(multi_template_specs, ohlcv_data)
        expected_ids = {s.id for s in multi_template_specs}

        assert expected_ids.issubset(set(result.columns)), (
            f"Missing columns: {expected_ids - set(result.columns)}"
        )
        assert set(result.columns) == expected_ids, (
            f"Extra columns: {set(result.columns) - expected_ids}"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestComputeFactorScoreEdgeCases:
    """Edge cases: empty specs, missing raw_data columns, single-row data."""

    def test_empty_specs_raises_value_error(self, ohlcv_data):
        """Empty specs list raises ValueError with descriptive message."""
        from trader_off.factor_mining.score import compute_factor_score

        with pytest.raises(ValueError, match="specs must not be empty"):
            compute_factor_score([], ohlcv_data)

    def test_missing_columns_produces_zeros(self, ohlcv_data, momentum_spec):
        """AC-FR0900-01: Missing required columns → compute_fn returns zeros,
        compute_factor_score still completes without error."""
        from trader_off.factor_mining.score import compute_factor_score

        # Remove the 'close' column that momentum_N needs
        data_no_close = ohlcv_data.drop("close")
        result = compute_factor_score([momentum_spec], data_no_close)

        assert result.height == data_no_close.height
        assert result.width == 1
        # All values should be 0.0 (fallback)
        arr = result.to_numpy()
        assert np.all(arr == 0.0) or np.all(np.isnan(arr) | (arr == 0.0)), (
            "Expected fallback to zeros when required columns are missing"
        )

    def test_single_row_data(self, momentum_spec):
        """AC-FR0900-01: Single-row input still produces valid output."""
        from trader_off.factor_mining.score import compute_factor_score

        single_row = pl.DataFrame(
            {
                "asset": ["000001.SZ"],
                "date": pl.Series("date", [pl.date(2026, 1, 5)], dtype=pl.Date),
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "volume": [1e6],
            }
        )
        result = compute_factor_score([momentum_spec], single_row)

        assert result.height == 1
        assert result.width == 1

    def test_duplicate_spec_ids_raises(self, ohlcv_data):
        """Duplicate spec IDs should not produce ambiguous columns."""
        from trader_off.factor_mining.expression import FactorSpec
        from trader_off.factor_mining.score import compute_factor_score

        # Create two specs with the same id (manually, since enumerate_factors
        # guarantees unique IDs)
        def dummy_compute(df: pl.DataFrame) -> pl.Series:
            return pl.Series("_factor", [1.0] * len(df), dtype=pl.Float64)

        spec_a = FactorSpec(
            id="same_id",
            template_name="dummy",
            category="momentum",
            formula="dummy",
            compute_fn=dummy_compute,
            params={},
        )
        spec_b = FactorSpec(
            id="same_id",
            template_name="dummy",
            category="momentum",
            formula="dummy",
            compute_fn=dummy_compute,
            params={},
        )

        with pytest.raises(ValueError, match="duplicate spec id"):
            compute_factor_score([spec_a, spec_b], ohlcv_data)

    def test_large_factor_set(self, ohlcv_data):
        """AC-FR0900-01: 30 specs produce 30 columns (selected_factor_count scenario)."""
        from trader_off.factor_mining.expression import FactorSpec
        from trader_off.factor_mining.score import compute_factor_score

        # Create 30 dummy specs
        def make_compute(val: float):
            def compute(df: pl.DataFrame) -> pl.Series:
                return pl.Series(f"f_{val}", [val] * len(df), dtype=pl.Float64)

            return compute

        specs = [
            FactorSpec(
                id=f"factor_{i:02d}",
                template_name="dummy",
                category="momentum",
                formula=f"dummy_{i}",
                compute_fn=make_compute(float(i)),
                params={},
            )
            for i in range(30)
        ]

        result = compute_factor_score(specs, ohlcv_data)

        assert result.width == 30, f"Expected 30 columns, got {result.width}"
        assert result.height == ohlcv_data.height
        assert len(result.columns) == 30


# ---------------------------------------------------------------------------
# Data alignment
# ---------------------------------------------------------------------------


class TestComputeFactorScoreDataAlignment:
    """AC-FR0900: Row ordering must be consistent for training label alignment."""

    def test_output_rows_correspond_to_input_rows(self, ohlcv_data, three_momentum_specs):
        """AC-FR0900: i-th row of output corresponds to i-th row of (sorted) input."""
        from trader_off.factor_mining.score import compute_factor_score

        # Sort the input as the function does
        sorted_data = ohlcv_data.sort(["asset", "date"])
        result = compute_factor_score(three_momentum_specs, ohlcv_data)

        # Verify row count matches
        assert result.height == sorted_data.height

        # Verify asset/date alignment by checking that factor values for
        # the same row produce consistent results across specs
        # (all factor values for row i should come from the same input row)
        first_spec = three_momentum_specs[0]
        # Re-compute single factor to get reference values
        ref_values = first_spec.compute_fn(sorted_data)
        col_name = first_spec.id

        # Compare ref values with result column (allow NaN equality)
        result_vals = result[col_name].to_numpy()
        ref_vals = ref_values.to_numpy()

        nan_mask = np.isnan(ref_vals)
        assert np.allclose(result_vals[~nan_mask], ref_vals[~nan_mask]), (
            "Factor values in output don't match expected values"
        )
