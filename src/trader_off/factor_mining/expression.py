"""Expression engine — parameterized factor enumeration (FR-0200).

Generates a list of FactorSpec instances by expanding parameter spaces
across registered FactorTemplates. Each FactorSpec includes a compute_fn
callable that accepts an OHLCV pl.DataFrame and returns a factor pl.Series.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Literal

import polars as pl

from trader_off.factor_mining.templates import (
    BoolParam,
    ChoiceParam,
    FactorTemplate,
    IntRangeParam,
    list_templates,
)

# ---------------------------------------------------------------------------
# Default parameter space — more granular than template-native expansions
# to reach ≥200 candidate factors (AC-FR0200-02).
# ---------------------------------------------------------------------------
DEFAULT_PARAM_SPACE: dict[str, list[int]] = {
    "N": list(range(1, 61)),
}

# ---------------------------------------------------------------------------
# FactorSpec dataclass (AC-FR0200-04)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FactorSpec:
    """A fully-expanded factor with id, formula, compute_fn, and params.

    Args:
        id: Unique identifier, e.g. "momentum_N_5".
        template_name: Name of the parent template.
        category: One of momentum, volatility, volume, fundamental.
        formula: Expanded formula string with parameters substituted.
        compute_fn: Callable accepting OHLCV pl.DataFrame → factor pl.Series.
        params: Expanded parameter values.
    """

    id: str
    template_name: str
    category: Literal["momentum", "volatility", "volume", "fundamental"]
    formula: str
    compute_fn: Callable[[pl.DataFrame], pl.Series]
    params: dict[str, int | str | float | bool]


# ---------------------------------------------------------------------------
# Main enumeration entry point
# ---------------------------------------------------------------------------


def enumerate_factors(
    templates: Iterable[FactorTemplate] | None = None,
    param_space: dict[str, list] | None = None,
    *,
    invalid_log_path: Path | None = None,
) -> list[FactorSpec]:
    """Enumerate all candidate factors by expanding parameter spaces.

    Args:
        templates: FactorTemplates to expand. Defaults to ``list_templates()``.
        param_space: Override mapping from param name to allowed values.
            When ``None``, uses ``DEFAULT_PARAM_SPACE`` (finer granularity).
        invalid_log_path: Path for ``invalid_combinations.json``.
            Defaults to ``invalid_combinations.json`` in CWD when needed.

    Returns:
        A list of FactorSpec instances, one per valid parameter combination.
    """
    if templates is None:
        templates = list_templates()
    else:
        templates = list(templates)

    if param_space is None:
        param_space = dict(DEFAULT_PARAM_SPACE)

    result: list[FactorSpec] = []
    invalid_records: list[dict[str, Any]] = []

    for template in templates:
        # Expand parameter values for this template
        param_combos = _expand_template_params(template, param_space, invalid_records)

        for params in param_combos:
            spec_id = _build_id(template.name, params)
            formula = _substitute_formula(template.formula, params)
            compute_fn = _build_compute_fn(template.name, template.fields, params)

            result.append(
                FactorSpec(
                    id=spec_id,
                    template_name=template.name,
                    category=template.category,
                    formula=formula,
                    compute_fn=compute_fn,
                    params=params,
                )
            )

    # Write invalid combinations log only when there are invalid records
    if invalid_records:
        log_path = invalid_log_path or Path("invalid_combinations.json")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w") as f:
            json.dump(invalid_records, f, indent=2)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _expand_template_params(
    template: FactorTemplate,
    param_space: dict[str, list],
    invalid_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Expand a template's params into a list of parameter dicts.

    For each param defined in the template:
      - If param name exists in ``param_space``, use that list for expansion.
      - Otherwise, use the template param's own ``expanded()`` or ``choices``.

    Combinations that violate the template's param constraint (e.g. N < min
    for IntRangeParam) are recorded to ``invalid_records`` and excluded.
    """
    param_names = list(template.params.keys())
    if not param_names:
        # No params: single combination with empty dict
        return [{}]

    # Build a list of (param_name, values) for expansion
    param_value_lists: list[list[tuple[str, Any]]] = []
    for pname in param_names:
        pdef = template.params[pname]

        if pname in param_space:
            # Use the provided param_space values
            candidate_values = list(param_space[pname])
        elif isinstance(pdef, IntRangeParam):
            candidate_values = pdef.expanded()
        elif isinstance(pdef, BoolParam):
            candidate_values = pdef.expanded()
        elif isinstance(pdef, ChoiceParam):
            candidate_values = list(pdef.choices)
        else:
            candidate_values = []  # pragma: no cover — unreachable with known param types

        # Filter valid values against template constraints
        valid_values: list[Any] = []
        for v in candidate_values:
            if _is_valid_param_value(pdef, v):
                valid_values.append(v)
            else:
                invalid_records.append(
                    {
                        "template": template.name,
                        "param": pname,
                        "value": v,
                        "reason": _invalid_reason(pdef, v),
                    }
                )

        if not valid_values:
            # No valid values for this param → template yields no combinations
            return []

        param_value_lists.append([(pname, v) for v in valid_values])

    # Cartesian product of all param value lists
    combos: list[dict[str, Any]] = []
    for combo in product(*param_value_lists):
        combos.append(dict(combo))

    return combos


def _is_valid_param_value(pdef: IntRangeParam | ChoiceParam | BoolParam, value: Any) -> bool:
    """Check if ``value`` is valid for the given parameter definition."""
    if isinstance(pdef, IntRangeParam):
        if not isinstance(value, int):
            return False
        return pdef.min <= value <= pdef.max
    if isinstance(pdef, BoolParam):
        return isinstance(value, bool)
    if isinstance(pdef, ChoiceParam):
        return value in pdef.choices
    return False  # pragma: no cover — unreachable with known param types


def _invalid_reason(pdef: IntRangeParam | ChoiceParam | BoolParam, value: Any) -> str:
    """Return a human-readable reason why ``value`` is invalid."""
    if isinstance(pdef, IntRangeParam):
        if not isinstance(value, int):
            return f"expected int, got {type(value).__name__}"
        if value < pdef.min:
            return f"value {value} < min {pdef.min}"
        if value > pdef.max:
            return f"value {value} > max {pdef.max}"
    if isinstance(pdef, BoolParam):
        return f"expected bool, got {type(value).__name__}"
    if isinstance(pdef, ChoiceParam):
        return f"{value!r} not in choices {pdef.choices}"
    return "unknown reason"  # pragma: no cover — unreachable with known param types


def _build_id(template_name: str, params: dict[str, Any]) -> str:
    """Build a unique factor ID from template name and sorted param values.

    Example: ``"momentum_N_5"``, ``"vol_N_20"``.
    """
    if not params:
        return template_name
    sorted_keys = sorted(params.keys())
    parts = [template_name] + [str(params[k]) for k in sorted_keys]
    return "_".join(parts)


def _substitute_formula(formula: str, params: dict[str, Any]) -> str:
    """Substitute parameter placeholders in the formula string.

    Uses Python ``str.format`` with the params dict.
    """
    return formula.format(**params)


# ---------------------------------------------------------------------------
# Compute function builders — one per template name
# ---------------------------------------------------------------------------

# Registry: template_name → builder function
_COMPUTE_BUILDERS: dict[str, Callable[..., Callable[[pl.DataFrame], pl.Series]]] = {}


def _register(name: str):
    """Decorator to register a compute function builder."""

    def decorator(fn):
        _COMPUTE_BUILDERS[name] = fn
        return fn

    return decorator


def _build_compute_fn(
    template_name: str,
    fields: list[str],
    params: dict[str, Any],
) -> Callable[[pl.DataFrame], pl.Series]:
    """Build a compute_fn for the given template and parameter values."""
    builder = _COMPUTE_BUILDERS.get(template_name)
    if builder is not None:
        return builder(fields, params)
    # Fallback: identity function returning first field's values
    return _build_fallback_fn(fields)


def _build_fallback_fn(fields: list[str]) -> Callable[[pl.DataFrame], pl.Series]:
    """Simple fallback: return the first field as factor."""
    field = fields[0] if fields else "close"

    def compute(df: pl.DataFrame) -> pl.Series:
        if field not in df.columns:
            return pl.Series("factor", [0.0] * len(df), dtype=pl.Float64)
        return df[field].cast(pl.Float64).alias("factor")

    return compute


# ---- Shared helper: shift-based ratio for momentum/volume ----
def _compute_shift_ratio(
    fields: list[str], params: dict[str, Any]
) -> Callable[[pl.DataFrame], pl.Series]:
    """Compute field[t] / field[t-N] - 1 grouped by asset."""
    field = fields[0]
    n = params.get("N", 5)

    def compute(df: pl.DataFrame) -> pl.Series:
        if field not in df.columns:
            return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)
        return df.sort(["asset", "date"]).with_columns(
            (pl.col(field) / pl.col(field).shift(n).over("asset") - 1).alias("_factor")
        )["_factor"]

    return compute


# ---- Template-specific compute builders ----


@_register("momentum_N")
def _momentum_n(fields: list[str], params: dict[str, Any]):
    return _compute_shift_ratio(fields, params)


@_register("excess_momentum_N")
def _excess_momentum_n(fields: list[str], params: dict[str, Any]):
    """Excess momentum: (close[t]/close[t-N]-1) - market_avg_return_N.
    Simplified as cross-sectional demeaned momentum."""
    field = fields[0]
    n = params.get("N", 5)

    def compute(df: pl.DataFrame) -> pl.Series:
        if field not in df.columns:
            return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)
        df = df.sort(["asset", "date"])
        raw = pl.col(field) / pl.col(field).shift(n).over("asset") - 1
        cs_mean = raw.mean().over("date")
        return df.with_columns((raw - cs_mean).alias("_factor"))["_factor"]

    return compute


@_register("momentum_accel_N")
def _momentum_accel_n(fields: list[str], params: dict[str, Any]):
    """Momentum acceleration: momentum_N - momentum_2N."""
    field = fields[0]
    n = params.get("N", 5)

    def compute(df: pl.DataFrame) -> pl.Series:
        if field not in df.columns:
            return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)
        df = df.sort(["asset", "date"])
        mom_n = pl.col(field) / pl.col(field).shift(n).over("asset") - 1
        mom_2n = pl.col(field) / pl.col(field).shift(2 * n).over("asset") - 1
        return df.with_columns((mom_n - mom_2n).alias("_factor"))["_factor"]

    return compute


@_register("vol_N")
def _vol_n(fields: list[str], params: dict[str, Any]):
    """Rolling std of daily returns over N days."""
    field = fields[0]
    n = params.get("N", 10)

    def compute(df: pl.DataFrame) -> pl.Series:
        if field not in df.columns:
            return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)
        return df.sort(["asset", "date"]).with_columns(
            pl.col(field).pct_change().rolling_std(n, min_samples=1).over("asset").alias("_factor"),
        )["_factor"]

    return compute


@_register("amplitude_N")
def _amplitude_n(fields: list[str], params: dict[str, Any]):
    """Rolling mean of (high-low)/close over N days."""
    n = params.get("N", 10)

    def compute(df: pl.DataFrame) -> pl.Series:
        required = {"high", "low", "close"}
        available = set(df.columns)
        if not required.issubset(available):
            return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)
        return df.sort(["asset", "date"]).with_columns(
            ((pl.col("high") - pl.col("low")) / pl.col("close"))
            .rolling_mean(n, min_samples=1)
            .over("asset")
            .alias("_factor"),
        )["_factor"]

    return compute


@_register("atr_N")
def _atr_n(fields: list[str], params: dict[str, Any]):
    """Rolling mean of true_range (high-low) over N days."""
    n = params.get("N", 10)

    def compute(df: pl.DataFrame) -> pl.Series:
        required = {"high", "low"}
        available = set(df.columns)
        if not required.issubset(available):
            return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)
        return df.sort(["asset", "date"]).with_columns(
            (pl.col("high") - pl.col("low"))
            .rolling_mean(n, min_samples=1)
            .over("asset")
            .alias("_factor")
        )["_factor"]

    return compute


@_register("volume_change_N")
def _volume_change_n(fields: list[str], params: dict[str, Any]):
    """Volume change ratio: volume[t]/volume[t-N]-1."""
    return _compute_shift_ratio(fields, params)


@_register("turnover_N")
def _turnover_n(fields: list[str], params: dict[str, Any]):
    """Rolling mean of turnover over N days."""
    field = fields[0]
    n = params.get("N", 5)

    def compute(df: pl.DataFrame) -> pl.Series:
        if field not in df.columns:
            return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)
        return df.sort(["asset", "date"]).with_columns(
            pl.col(field).rolling_mean(n, min_samples=1).over("asset").alias("_factor")
        )["_factor"]

    return compute


@_register("vp_corr_N")
def _vp_corr_n(fields: list[str], params: dict[str, Any]):
    """Rolling correlation between volume and close over N days.
    Simplified using rolling_cov / (rolling_std_vol * rolling_std_close)."""
    n = params.get("N", 5)

    def compute(df: pl.DataFrame) -> pl.Series:
        required = {"volume", "close"}
        available = set(df.columns)
        if not required.issubset(available):
            return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)
        df = df.sort(["asset", "date"])
        vol_std = pl.col("volume").rolling_std(n, min_samples=n).over("asset")
        close_std = pl.col("close").rolling_std(n, min_samples=n).over("asset")
        vol_mean = pl.col("volume").rolling_mean(n, min_samples=n).over("asset")
        close_mean = pl.col("close").rolling_mean(n, min_samples=n).over("asset")
        cov = (
            ((pl.col("volume") - vol_mean) * (pl.col("close") - close_mean))
            .rolling_mean(n, min_samples=n)
            .over("asset")
        )
        return df.with_columns((cov / (vol_std * close_std + 1e-9)).alias("_factor"))["_factor"]

    return compute


# ---- Fundamental template compute builders — simple pass-through ----


@_register("ep")
def _ep(fields: list[str], params: dict[str, Any]):
    """1/PE factor."""

    def compute(df: pl.DataFrame) -> pl.Series:
        if "pe" in df.columns:
            return (1.0 / df["pe"].cast(pl.Float64).replace(0, None)).alias("_factor")
        return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)

    return compute


@_register("bp")
def _bp(fields: list[str], params: dict[str, Any]):
    """1/PB factor."""

    def compute(df: pl.DataFrame) -> pl.Series:
        if "pb" in df.columns:
            return (1.0 / df["pb"].cast(pl.Float64).replace(0, None)).alias("_factor")
        return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)

    return compute


@_register("roe")
def _roe(fields: list[str], params: dict[str, Any]):
    """ROE factor."""

    def compute(df: pl.DataFrame) -> pl.Series:
        if "roe" in df.columns:
            return df["roe"].cast(pl.Float64).alias("_factor")
        return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)

    return compute


@_register("revenue_growth")
def _revenue_growth(fields: list[str], params: dict[str, Any]):
    """Revenue growth factor."""

    def compute(df: pl.DataFrame) -> pl.Series:
        if "revenue_growth" in df.columns:
            return df["revenue_growth"].cast(pl.Float64).alias("_factor")
        return pl.Series("_factor", [0.0] * len(df), dtype=pl.Float64)

    return compute
