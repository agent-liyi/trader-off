"""Factor template registry — 4 categories × ≥3 templates per category (FR-0100).

Defines:
    FactorTemplate — immutable template metadata
    IntRangeParam, ChoiceParam, BoolParam — parameter space definitions
    list_templates() — enumerate all registered templates
    FACTOR_TEMPLATE_VERSION — template library version constant
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Version constant (AC-FR0100-04)
# ---------------------------------------------------------------------------
FACTOR_TEMPLATE_VERSION: str = "v1"

# ---------------------------------------------------------------------------
# Param classes (AC-FR0100-02)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IntRangeParam:
    """Integer range parameter with min, max, step.

    Args:
        name: Parameter name.
        min: Minimum value (inclusive).
        max: Maximum value (inclusive).
        step: Step size between values.
    """

    name: str
    min: int
    max: int
    step: int = 1

    def expanded(self) -> list[int]:
        """Return the full list of valid integer values in the range."""
        result = list(range(self.min, self.max + 1, self.step))
        # Ensure max is included when (max - min) % step != 0
        if not result or result[-1] != self.max:
            result.append(self.max)
        return result


@dataclass(frozen=True)
class ChoiceParam:
    """Discrete choice parameter with a fixed set of options.

    Args:
        name: Parameter name.
        choices: List of valid choices (str, int, or float).
    """

    name: str
    choices: list[str | int | float]


@dataclass(frozen=True)
class BoolParam:
    """Boolean parameter that expands to [False, True].

    Args:
        name: Parameter name.
    """

    name: str

    def expanded(self) -> list[bool]:
        """Return [False, True]."""
        return [False, True]


# ---------------------------------------------------------------------------
# FactorTemplate (AC-FR0100-01)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FactorTemplate:
    """Immutable factor template metadata.

    Args:
        name: Unique template name, e.g. "momentum_N".
        category: One of momentum, volatility, volume, fundamental.
        fields: OHLCV/fundamental column names referenced in the formula.
        params: Parameter definitions (IntRangeParam, ChoiceParam, BoolParam).
        formula: Human-readable formula string with parameter placeholders.
    """

    name: str
    category: Literal["momentum", "volatility", "volume", "fundamental"]
    fields: list[str]
    params: dict[str, IntRangeParam | ChoiceParam | BoolParam]
    formula: str


# ---------------------------------------------------------------------------
# Template definitions (4 categories × ≥3 templates)
# ---------------------------------------------------------------------------

_TEMPLATES: list[FactorTemplate] = [
    # ---- Momentum (≥3) ----
    FactorTemplate(
        name="momentum_N",
        category="momentum",
        fields=["close"],
        params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
        formula="close[t]/close[t-N]-1",
    ),
    FactorTemplate(
        name="excess_momentum_N",
        category="momentum",
        fields=["close"],
        params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
        formula="(close[t]/close[t-N]-1) - market_avg_return_N",
    ),
    FactorTemplate(
        name="momentum_accel_N",
        category="momentum",
        fields=["close"],
        params={"N": IntRangeParam(name="N", min=5, max=60, step=5)},
        formula="momentum_N - momentum_2N",
    ),
    # ---- Volatility (≥3) ----
    FactorTemplate(
        name="vol_N",
        category="volatility",
        fields=["close"],
        params={"N": IntRangeParam(name="N", min=10, max=60, step=10)},
        formula="std(daily_returns, N)",
    ),
    FactorTemplate(
        name="amplitude_N",
        category="volatility",
        fields=["high", "low", "close"],
        params={"N": IntRangeParam(name="N", min=10, max=60, step=10)},
        formula="rolling_mean((high-low)/close, N)",
    ),
    FactorTemplate(
        name="atr_N",
        category="volatility",
        fields=["high", "low", "close"],
        params={"N": IntRangeParam(name="N", min=10, max=60, step=10)},
        formula="rolling_mean(true_range, N)",
    ),
    # ---- Volume (≥3) ----
    FactorTemplate(
        name="volume_change_N",
        category="volume",
        fields=["volume"],
        params={"N": IntRangeParam(name="N", min=5, max=20, step=5)},
        formula="volume[t]/volume[t-N]-1",
    ),
    FactorTemplate(
        name="turnover_N",
        category="volume",
        fields=["turnover"],
        params={"N": IntRangeParam(name="N", min=5, max=20, step=5)},
        formula="rolling_mean(turnover, N)",
    ),
    FactorTemplate(
        name="vp_corr_N",
        category="volume",
        fields=["volume", "close"],
        params={"N": IntRangeParam(name="N", min=5, max=20, step=5)},
        formula="rolling_corr(volume, close, N)",
    ),
    # ---- Fundamental (≥3) ----
    FactorTemplate(
        name="ep",
        category="fundamental",
        fields=["pe"],
        params={},
        formula="1/PE",
    ),
    FactorTemplate(
        name="bp",
        category="fundamental",
        fields=["pb"],
        params={},
        formula="1/PB",
    ),
    FactorTemplate(
        name="roe",
        category="fundamental",
        fields=["roe"],
        params={},
        formula="ROE",
    ),
    FactorTemplate(
        name="revenue_growth",
        category="fundamental",
        fields=["revenue_growth"],
        params={},
        formula="revenue_growth",
    ),
]


def list_templates() -> list[FactorTemplate]:
    """Return all registered factor templates (≥12 across 4 categories).

    Returns:
        A list of FactorTemplate instances. The list includes at least 3
        templates for each of the 4 categories: momentum, volatility, volume,
        fundamental.
    """
    return list(_TEMPLATES)
