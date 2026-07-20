"""Unit tests for factor expression engine — parameterized enumeration (FR-0200)."""

import json

import polars as pl
import pytest

from trader_off.factor_mining.templates import (
    BoolParam,
    ChoiceParam,
    FactorTemplate,
    IntRangeParam,
)

# ---------------------------------------------------------------------------
# AC-FR0200-01: Custom templates + explicit param_space → 7 unique FactorSpecs
# ---------------------------------------------------------------------------


class TestEnumerateFactorsAC1:
    """AC-FR0200-01: 2 templates (momentum_N, vol_N) with custom param_space
    yields 7 FactorSpecs with unique IDs matching the expanded parameter values."""

    @pytest.fixture
    def templates(self):
        t1 = FactorTemplate(
            name="momentum_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="close[t]/close[t-{N}]-1",
        )
        t2 = FactorTemplate(
            name="vol_N",
            category="volatility",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=10, max=60, step=10)},
            formula="std(daily_returns, {N})",
        )
        return [t1, t2]

    def test_ac_fr0200_01_two_templates_seven_factors(self, templates):
        """AC-FR0200-01: 4 momentum_N + 3 vol_N = 7 total, all IDs unique.
        vol_N min=10 so N=5 is invalid → only 3 for vol_N."""
        from trader_off.factor_mining.expression import enumerate_factors

        param_space = {"N": [5, 10, 20, 60]}
        result = enumerate_factors(templates, param_space)

        assert len(result) == 7, f"Expected 7 factors, got {len(result)}"
        ids = [s.id for s in result]
        assert len(set(ids)) == 7, f"IDs not unique: {ids}"

        # Verify expected IDs
        expected_ids = {
            "momentum_N_5",
            "momentum_N_10",
            "momentum_N_20",
            "momentum_N_60",
            "vol_N_10",
            "vol_N_20",
            "vol_N_60",
        }
        assert set(ids) == expected_ids, f"Unexpected IDs: {set(ids)}"

    def test_ac_fr0200_01_all_are_factorspec_instances(self, templates):
        """AC-FR0200-01: All results are FactorSpec dataclass instances."""
        from trader_off.factor_mining.expression import FactorSpec, enumerate_factors

        result = enumerate_factors(templates, {"N": [5, 10]})
        assert len(result) == 3  # 2 momentum + 1 vol (N=5 invalid for vol)
        assert all(isinstance(s, FactorSpec) for s in result)


# ---------------------------------------------------------------------------
# AC-FR0200-02: Default templates + default param space ≥ 200
# ---------------------------------------------------------------------------


class TestEnumerateFactorsAC2:
    """AC-FR0200-02: Default templates with default parameter space
    produce at least 200 candidate FactorSpecs."""

    def test_ac_fr0200_02_default_ge_200(self):
        """AC-FR0200-02: Without arguments, enumerate_factors returns ≥200 factors."""
        from trader_off.factor_mining.expression import enumerate_factors

        result = enumerate_factors()
        assert len(result) >= 200, f"Expected ≥200 factors, got {len(result)}"
        ids = [s.id for s in result]
        assert len(set(ids)) == len(result), f"IDs not unique: {len(set(ids))} != {len(result)}"


# ---------------------------------------------------------------------------
# AC-FR0200-03: Invalid parameter combinations skipped and logged
# ---------------------------------------------------------------------------


class TestEnumerateFactorsAC3:
    """AC-FR0200-03: N <= 0 or out-of-range combos are skipped and
    recorded to invalid_combinations.json."""

    @pytest.fixture
    def momentum_template(self):
        return FactorTemplate(
            name="momentum_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="close[t]/close[t-{N}]-1",
        )

    def test_ac_fr0200_03_invalid_n_skipped(self, momentum_template, tmp_path):
        """AC-FR0200-03: N=-5 and N=0 are filtered; valid N=5,10,60 remain.
        Recorded to invalid_combinations.json in tmp_path."""
        from trader_off.factor_mining.expression import enumerate_factors

        param_space = {"N": [-5, 0, 5, 10, 60]}
        result = enumerate_factors(
            [momentum_template],
            param_space,
            invalid_log_path=tmp_path / "invalid_combinations.json",
        )

        valid_ns = {s.params["N"] for s in result}
        assert valid_ns == {5, 10, 60}, f"Expected {{5, 10, 60}}, got {valid_ns}"
        assert len(result) == 3

    def test_ac_fr0200_03_invalid_combinations_json_exists(self, momentum_template, tmp_path):
        """AC-FR0200-03: invalid_combinations.json is written with skipped records."""
        from trader_off.factor_mining.expression import enumerate_factors

        param_space = {"N": [-5, 0, 5]}
        enumerate_factors(
            [momentum_template],
            param_space,
            invalid_log_path=tmp_path / "invalid_combinations.json",
        )

        log_path = tmp_path / "invalid_combinations.json"
        assert log_path.exists(), f"Expected {log_path} to exist"

        with open(log_path) as f:
            records = json.load(f)
        assert isinstance(records, list), f"Expected JSON list, got {type(records)}"
        assert len(records) >= 2, f"Expected ≥2 invalid records, got {len(records)}"
        assert all(isinstance(r, dict) for r in records)
        assert all("template" in r for r in records)

    def test_ac_fr0200_03_no_invalid_log_when_all_valid(self, momentum_template, tmp_path):
        """AC-FR0200-03: When all combos are valid, no invalid_combinations.json
        is created."""
        from trader_off.factor_mining.expression import enumerate_factors

        param_space = {"N": [5, 10]}
        log_path = tmp_path / "invalid_combinations.json"
        result = enumerate_factors([momentum_template], param_space, invalid_log_path=log_path)
        assert len(result) == 2
        assert not log_path.exists(), "No invalid log when all combos valid"


# ---------------------------------------------------------------------------
# AC-FR0200-04: FactorSpec fields and compute_fn callability
# ---------------------------------------------------------------------------


class TestEnumerateFactorsAC4:
    """AC-FR0200-04: Each FactorSpec has id, template_name, category, formula,
    compute_fn, params with correct types; compute_fn is callable."""

    @pytest.fixture
    def momentum_template(self):
        return FactorTemplate(
            name="momentum_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="close[t]/close[t-{N}]-1",
        )

    def test_ac_fr0200_04_factorspec_fields(self, momentum_template):
        """AC-FR0200-04: FactorSpec dataclass has all required fields with
        correct types and values."""
        from trader_off.factor_mining.expression import enumerate_factors

        result = enumerate_factors([momentum_template], {"N": [5]})
        assert len(result) == 1
        s = result[0]

        # Type assertions
        assert isinstance(s.id, str), f"id must be str, got {type(s.id)}"
        assert s.id == "momentum_N_5", f"Expected 'momentum_N_5', got '{s.id}'"
        assert isinstance(s.template_name, str)
        assert s.template_name == "momentum_N"
        assert isinstance(s.category, str)
        assert s.category == "momentum"
        assert isinstance(s.formula, str)
        assert len(s.formula) > 0, "formula must be non-empty"
        assert callable(s.compute_fn), "compute_fn must be callable"
        assert isinstance(s.params, dict)
        assert s.params.get("N") == 5

    def test_ac_fr0200_04_compute_fn_callable_with_dataframe(self, momentum_template):
        """AC-FR0200-04: compute_fn accepts a pl.DataFrame and returns a pl.Series."""
        from trader_off.factor_mining.expression import enumerate_factors

        result = enumerate_factors([momentum_template], {"N": [5]})
        s = result[0]

        df = pl.DataFrame(
            {
                "asset": ["A"] * 10,
                "date": list(range(10)),
                "close": [100.0 + i for i in range(10)],
            }
        )

        factor = s.compute_fn(df)
        assert isinstance(factor, pl.Series), (
            f"compute_fn must return pl.Series, got {type(factor)}"
        )

    def test_ac_fr0200_04_all_default_compute_fns_callable(self):
        """AC-FR0200-04: All compute_fn from default enumeration are callable
        with non-empty formulas."""
        from trader_off.factor_mining.expression import enumerate_factors

        result = enumerate_factors()
        for s in result[:30]:  # Sample first 30
            assert callable(s.compute_fn), f"{s.id} compute_fn is not callable"
            assert isinstance(s.formula, str) and s.formula, f"{s.id} formula is empty or non-str"

    def test_ac_fr0200_04_compute_fn_volume_template(self):
        """AC-FR0200-04: volume_change_N compute_fn works with volume field."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="volume_change_N",
            category="volume",
            fields=["volume"],
            params={"N": IntRangeParam(name="N", min=5, max=20, step=5)},
            formula="volume[t]/volume[t-{N}]-1",
        )
        result = enumerate_factors([t], {"N": [5]})
        s = result[0]

        df = pl.DataFrame(
            {
                "asset": ["B"] * 10,
                "date": list(range(10)),
                "volume": [1000.0 + i * 10 for i in range(10)],
            }
        )
        factor = s.compute_fn(df)
        assert isinstance(factor, pl.Series)

    def test_ac_fr0200_04_compute_fn_fundamental_templates(self):
        """AC-FR0200-04: Fundamental template compute_fns produce output
        for ep, bp, roe, revenue_growth."""
        from trader_off.factor_mining.expression import enumerate_factors
        from trader_off.factor_mining.templates import list_templates

        fundamental = [t for t in list_templates() if t.category == "fundamental"]
        result = enumerate_factors(fundamental, {})
        assert len(result) >= 4

        for s in result:
            assert callable(s.compute_fn)
            # Test with relevant columns
            df = pl.DataFrame(
                {
                    "asset": ["C"] * 3,
                    "date": [1, 2, 3],
                    "pe": [10.0, 20.0, 30.0],
                    "pb": [1.0, 2.0, 3.0],
                    "roe": [0.1, 0.15, 0.2],
                    "revenue_growth": [0.05, 0.08, 0.12],
                }
            )
            factor = s.compute_fn(df)
            assert isinstance(factor, pl.Series)

    def test_ac_fr0200_04_compute_fn_missing_field_fallback(self):
        """AC-FR0200-04: compute_fn with missing fields returns zeros gracefully."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="vol_N",
            category="volatility",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=10, max=60, step=10)},
            formula="std(daily_returns, {N})",
        )
        result = enumerate_factors([t], {"N": [10]})
        s = result[0]

        # DataFrame without "close" column
        df = pl.DataFrame(
            {
                "asset": ["D"] * 5,
                "date": list(range(5)),
            }
        )
        factor = s.compute_fn(df)
        assert isinstance(factor, pl.Series)

    def test_ac_fr0200_04_compute_fn_amplitude_atr_templates(self):
        """AC-FR0200-04: amplitude_N and atr_N compute_fns handle OHLC data."""
        from trader_off.factor_mining.expression import enumerate_factors

        # Test amplitude_N
        amp_t = FactorTemplate(
            name="amplitude_N",
            category="volatility",
            fields=["high", "low", "close"],
            params={"N": IntRangeParam(name="N", min=10, max=60, step=10)},
            formula="rolling_mean((high-low)/close, {N})",
        )
        amp_result = enumerate_factors([amp_t], {"N": [10]})
        df_ohlc = pl.DataFrame(
            {
                "asset": ["E"] * 15,
                "date": list(range(15)),
                "high": [101.0 + i for i in range(15)],
                "low": [99.0 + i for i in range(15)],
                "close": [100.0 + i for i in range(15)],
            }
        )
        factor = amp_result[0].compute_fn(df_ohlc)
        assert isinstance(factor, pl.Series)

        # Test atr_N
        atr_t = FactorTemplate(
            name="atr_N",
            category="volatility",
            fields=["high", "low", "close"],
            params={"N": IntRangeParam(name="N", min=10, max=60, step=10)},
            formula="rolling_mean(true_range, {N})",
        )
        atr_result = enumerate_factors([atr_t], {"N": [10]})
        factor = atr_result[0].compute_fn(df_ohlc)
        assert isinstance(factor, pl.Series)

    def test_ac_fr0200_04_compute_fn_turnover_vpcorr(self):
        """AC-FR0200-04: turnover_N and vp_corr_N compute_fns work."""
        from trader_off.factor_mining.expression import enumerate_factors

        # turnover_N
        to_t = FactorTemplate(
            name="turnover_N",
            category="volume",
            fields=["turnover"],
            params={"N": IntRangeParam(name="N", min=5, max=20, step=5)},
            formula="rolling_mean(turnover, {N})",
        )
        to_result = enumerate_factors([to_t], {"N": [5]})
        df_vol = pl.DataFrame(
            {
                "asset": ["F"] * 10,
                "date": list(range(10)),
                "turnover": [0.01 + i * 0.001 for i in range(10)],
            }
        )
        factor = to_result[0].compute_fn(df_vol)
        assert isinstance(factor, pl.Series)

        # vp_corr_N
        vp_t = FactorTemplate(
            name="vp_corr_N",
            category="volume",
            fields=["volume", "close"],
            params={"N": IntRangeParam(name="N", min=5, max=20, step=5)},
            formula="rolling_corr(volume, close, {N})",
        )
        vp_result = enumerate_factors([vp_t], {"N": [5]})
        df_vp = pl.DataFrame(
            {
                "asset": ["G"] * 10,
                "date": list(range(10)),
                "volume": [1000.0 + i * 10 for i in range(10)],
                "close": [100.0 + i * 0.5 for i in range(10)],
            }
        )
        factor = vp_result[0].compute_fn(df_vp)
        assert isinstance(factor, pl.Series)

    def test_ac_fr0200_04_compute_fn_excess_and_accel_momentum(self):
        """AC-FR0200-04: excess_momentum_N and momentum_accel_N compute_fns."""
        from trader_off.factor_mining.expression import enumerate_factors

        # excess_momentum_N
        ex_t = FactorTemplate(
            name="excess_momentum_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="(close[t]/close[t-{N}]-1) - market_avg_return_N",
        )
        ex_result = enumerate_factors([ex_t], {"N": [5]})
        df = pl.DataFrame(
            {
                "asset": ["H"] * 10,
                "date": list(range(10)),
                "close": [100.0 + i for i in range(10)],
            }
        )
        factor = ex_result[0].compute_fn(df)
        assert isinstance(factor, pl.Series)

        # momentum_accel_N
        acc_t = FactorTemplate(
            name="momentum_accel_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="momentum_N - momentum_2N",
        )
        acc_result = enumerate_factors([acc_t], {"N": [5]})
        factor = acc_result[0].compute_fn(df)
        assert isinstance(factor, pl.Series)


# ---------------------------------------------------------------------------
# Additional coverage tests for BoolParam / ChoiceParam validation
# ---------------------------------------------------------------------------


class TestParamValidation:
    """Coverage: BoolParam and ChoiceParam validation / invalidation paths."""

    def test_boolparam_validation(self):
        """BoolParam: valid bool passes, non-bool fails validation."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="use_adj",
            category="momentum",
            fields=["close"],
            params={"use_adj": BoolParam(name="use_adj")},
            formula="price_adj_{use_adj}",
        )
        # Valid bool values
        result = enumerate_factors([t], {"use_adj": [True, False]})
        assert len(result) == 2

    def test_boolparam_invalid_rejected(self):
        """BoolParam: non-bool values (int, str) are rejected and logged."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="use_adj",
            category="momentum",
            fields=["close"],
            params={"use_adj": BoolParam(name="use_adj")},
            formula="price_adj_{use_adj}",
        )
        result = enumerate_factors([t], {"use_adj": [True, 1, "yes"]})
        # Only True passes
        assert len(result) == 1

    def test_choiceparam_validation(self):
        """ChoiceParam: valid choices pass, invalid ones rejected."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="method_choice",
            category="momentum",
            fields=["close"],
            params={"method": ChoiceParam(name="method", choices=["pearson", "spearman"])},
            formula="corr_method_{method}",
        )
        param_space = {"method": ["pearson", "spearman", "kendall"]}
        result = enumerate_factors([t], param_space)
        assert len(result) == 2  # kendall rejected

    def test_no_param_template_default_enumeration(self):
        """Templates with no params (e.g., fundamental) enumerate to 1 spec per template."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="ep",
            category="fundamental",
            fields=["pe"],
            params={},
            formula="1/PE",
        )
        result = enumerate_factors([t], {})
        assert len(result) == 1
        assert result[0].id == "ep"

    def test_uneven_step_int_range_param_value_rejected(self, tmp_path):
        """IntRangeParam: param_space value outside [min,max] is rejected."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="momentum_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="close[t]/close[t-{N}]-1",
        )
        param_space = {"N": [70, 100]}  # both > max=60
        result = enumerate_factors(
            [t],
            param_space,
            invalid_log_path=tmp_path / "invalid_combinations.json",
        )
        assert len(result) == 0

    def test_fallback_compute_fn(self):
        """Fallback compute_fn for templates with no registered builder."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="unknown_factor",
            category="momentum",
            fields=["some_field"],
            params={},
            formula="unknown",
        )
        result = enumerate_factors([t], {})
        assert len(result) == 1
        s = result[0]
        assert callable(s.compute_fn)
        # Fallback should return zeros for missing column
        df = pl.DataFrame({"asset": ["X"] * 3, "date": [1, 2, 3]})
        factor = s.compute_fn(df)
        assert isinstance(factor, pl.Series)

    def test_fallback_compute_fn_with_existing_field(self):
        """Fallback compute_fn returns the first field when it exists."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="unknown_factor",
            category="momentum",
            fields=["my_value"],
            params={},
            formula="unknown",
        )
        result = enumerate_factors([t], {})
        s = result[0]
        df = pl.DataFrame({"asset": ["X"] * 3, "date": [1, 2, 3], "my_value": [10.0, 20.0, 30.0]})
        factor = s.compute_fn(df)
        assert isinstance(factor, pl.Series)
        assert factor[0] == 10.0

    def test_intrangeparam_non_int_value_rejected(self, tmp_path):
        """IntRangeParam with non-int values (string) in param_space are
        rejected and logged."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="momentum_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="close[t]/close[t-{N}]-1",
        )
        result = enumerate_factors(
            [t],
            {"N": [5, "invalid", 10.5]},
            invalid_log_path=tmp_path / "invalid_combinations.json",
        )
        assert len(result) == 1  # Only N=5 is valid
        assert result[0].params["N"] == 5

    def test_intrangeparam_default_expansion_without_param_space(self):
        """IntRangeParam uses its own expanded() when param not in param_space."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="test_factor",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=1, max=3, step=1)},
            formula="test_{N}",
        )
        # param_space is empty — "N" not in it → fallback to pdef.expanded()
        result = enumerate_factors([t], {})
        assert len(result) == 3
        assert {s.params["N"] for s in result} == {1, 2, 3}

    def test_boolparam_default_expansion_without_param_space(self):
        """BoolParam uses its own expanded() when param not in param_space."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="use_adj",
            category="momentum",
            fields=["close"],
            params={"use_adj": BoolParam(name="use_adj")},
            formula="price_{use_adj}",
        )
        result = enumerate_factors([t], {})
        assert len(result) == 2  # False and True

    def test_choiceparam_default_expansion_without_param_space(self):
        """ChoiceParam uses its own choices when param not in param_space."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="method",
            category="momentum",
            fields=["close"],
            params={"method": ChoiceParam(name="method", choices=["a", "b"])},
            formula="method_{method}",
        )
        result = enumerate_factors([t], {})
        assert len(result) == 2

    def test_compute_fn_momentum_executed(self):
        """momentum_N compute_fn produces actual numeric output."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="momentum_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="close[t]/close[t-{N}]-1",
        )
        result = enumerate_factors([t], {"N": [5]})
        s = result[0]
        df = pl.DataFrame(
            {
                "asset": ["A"] * 10,
                "date": list(range(10)),
                "close": [100.0 + i for i in range(10)],
            }
        )
        factor = s.compute_fn(df)
        assert isinstance(factor, pl.Series)
        # First 5 values should be null (shift), later should be non-null
        assert factor.null_count() >= 5

    def test_fundamental_compute_fn_each(self):
        """Each fundamental compute_fn (ep, bp, roe, revenue_growth)
        produces output."""
        from trader_off.factor_mining.expression import enumerate_factors
        from trader_off.factor_mining.templates import list_templates

        fundamental = [t for t in list_templates() if t.category == "fundamental"]
        result = enumerate_factors(fundamental, {})

        for s in result:
            df = pl.DataFrame(
                {
                    "asset": ["C"] * 3,
                    "date": [1, 2, 3],
                    "pe": [10.0, 20.0, 30.0],
                    "pb": [1.0, 2.0, 3.0],
                    "roe": [0.1, 0.15, 0.2],
                    "revenue_growth": [0.05, 0.08, 0.12],
                }
            )
            factor = s.compute_fn(df)
            assert isinstance(factor, pl.Series), f"compute_fn for {s.id} failed"
            assert len(factor) == 3


# ---------------------------------------------------------------------------
# Coverage: missing-field fallback for each compute_fn type
# ---------------------------------------------------------------------------


class TestComputeFnMissingFields:
    """Each compute_fn handles missing columns gracefully (returns zeros)."""

    @pytest.fixture
    def empty_df(self):
        return pl.DataFrame({"asset": ["X"] * 3, "date": [1, 2, 3]})

    def test_shift_ratio_missing_field(self, empty_df):
        """_compute_shift_ratio: missing field returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="momentum_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="ratio",
        )
        result = enumerate_factors([t], {"N": [5]})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_excess_momentum_missing_field(self, empty_df):
        """excess_momentum_N: missing field returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="excess_momentum_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="excess",
        )
        result = enumerate_factors([t], {"N": [5]})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_momentum_accel_missing_field(self, empty_df):
        """momentum_accel_N: missing field returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="momentum_accel_N",
            category="momentum",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
            formula="accel",
        )
        result = enumerate_factors([t], {"N": [5]})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_amplitude_missing_fields(self, empty_df):
        """amplitude_N: missing high/low/close returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="amplitude_N",
            category="volatility",
            fields=["high", "low", "close"],
            params={"N": IntRangeParam(name="N", min=10, max=60, step=10)},
            formula="amplitude",
        )
        result = enumerate_factors([t], {"N": [10]})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_atr_missing_fields(self, empty_df):
        """atr_N: missing high/low returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="atr_N",
            category="volatility",
            fields=["high", "low", "close"],
            params={"N": IntRangeParam(name="N", min=10, max=60, step=10)},
            formula="atr",
        )
        result = enumerate_factors([t], {"N": [10]})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_turnover_missing_field(self, empty_df):
        """turnover_N: missing field returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="turnover_N",
            category="volume",
            fields=["turnover"],
            params={"N": IntRangeParam(name="N", min=5, max=20, step=5)},
            formula="turnover",
        )
        result = enumerate_factors([t], {"N": [5]})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_vp_corr_missing_fields(self, empty_df):
        """vp_corr_N: missing volume/close returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="vp_corr_N",
            category="volume",
            fields=["volume", "close"],
            params={"N": IntRangeParam(name="N", min=5, max=20, step=5)},
            formula="vp_corr",
        )
        result = enumerate_factors([t], {"N": [5]})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_ep_missing_field(self, empty_df):
        """ep: missing pe column returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="ep",
            category="fundamental",
            fields=["pe"],
            params={},
            formula="1/PE",
        )
        result = enumerate_factors([t], {})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_bp_missing_field(self, empty_df):
        """bp: missing pb column returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="bp",
            category="fundamental",
            fields=["pb"],
            params={},
            formula="1/PB",
        )
        result = enumerate_factors([t], {})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_roe_missing_field(self, empty_df):
        """roe: missing roe column returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="roe",
            category="fundamental",
            fields=["roe"],
            params={},
            formula="ROE",
        )
        result = enumerate_factors([t], {})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_revenue_growth_missing_field(self, empty_df):
        """revenue_growth: missing revenue_growth column returns zeros."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="revenue_growth",
            category="fundamental",
            fields=["revenue_growth"],
            params={},
            formula="revenue_growth",
        )
        result = enumerate_factors([t], {})
        factor = result[0].compute_fn(empty_df)
        assert isinstance(factor, pl.Series)

    def test_vol_n_with_valid_data(self):
        """vol_N: with valid close column, returns a computed Series."""
        from trader_off.factor_mining.expression import enumerate_factors

        t = FactorTemplate(
            name="vol_N",
            category="volatility",
            fields=["close"],
            params={"N": IntRangeParam(name="N", min=10, max=60, step=10)},
            formula="std(daily_returns, {N})",
        )
        result = enumerate_factors([t], {"N": [10]})
        df = pl.DataFrame(
            {
                "asset": ["Z"] * 20,
                "date": list(range(20)),
                "close": [100.0 + i * 0.5 for i in range(20)],
            }
        )
        factor = result[0].compute_fn(df)
        assert isinstance(factor, pl.Series)
        assert len(factor) == 20
