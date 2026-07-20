"""Performance decay detection (FR-1900, Round-2: IC-only).

Per interfaces.md §1.7, §3.12:
- TriggerDecision: dataclass for IC-based performance decisions.
- detect_perf_decay: pure function for rolling-window IC evaluation.
- PerfMonitor: class wrapping detect_perf_decay with a configurable IC provider.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from trader_off.scheduler.core import SchedulerConfig


# ---------------------------------------------------------------------------
# TriggerDecision dataclass (interfaces.md §1.7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TriggerDecision:
    """IC-based performance decay decision (Round-2: IC-only).

    Per interfaces.md §1.7.  Round-2 lock: no sharpe field; notes
    always contains "ic_only".

    Attributes:
        should_retrain: Whether retraining is recommended.
        reason: Trigger reason — "ok", "ic_below_floor", or "ic_drop_ratio_exceeded".
        suggested_mode: Retraining mode to use if triggered.
        computation_time_sec: Wall time for detection (<1.0 required per AC-4).
        notes: Always contains "ic_only" per Round-2 lock.
    """

    should_retrain: bool
    reason: Literal["ok", "ic_below_floor", "ic_drop_ratio_exceeded"]
    suggested_mode: Literal["full", "incremental"]
    computation_time_sec: float
    notes: str


# ---------------------------------------------------------------------------
# detect_perf_decay — pure function
# ---------------------------------------------------------------------------


def detect_perf_decay(
    recent_ic: list[float],
    *,
    reference_ic_mean: float | None = None,
    ic_floor: float = 0.005,
    ic_drop_ratio: float = 0.3,
    window: int = 20,
) -> TriggerDecision:
    """Evaluate IC-based performance decay (Round-2: IC-only, no Sharpe).

    Computes the rolling mean of the most recent `window` IC values and
    evaluates two trigger conditions:

    1. **ic_below_floor**: rolling mean < ic_floor → immediate trigger.
    2. **ic_drop_ratio_exceeded**: relative drop from reference mean
       exceeds ic_drop_ratio.

    Condition (1) takes priority over (2).

    Args:
        recent_ic: Sequence of recent IC values (most recent last).
        reference_ic_mean: Baseline IC mean for drop-ratio evaluation.
            If None or ≤0, drop-ratio check is skipped.
        ic_floor: Absolute IC floor threshold (default 0.005).
        ic_drop_ratio: Maximum allowed relative IC drop (default 0.3).
        window: Rolling window size for the moving mean (default 20).

    Returns:
        TriggerDecision with should_retrain, reason, and notes="ic_only".
    """
    t0 = time.perf_counter()

    # Extract the rolling window
    if len(recent_ic) > window:
        data = recent_ic[-window:]
    else:
        data = recent_ic

    # No data → safe default
    if not data:
        elapsed = time.perf_counter() - t0
        return TriggerDecision(
            should_retrain=False,
            reason="ok",
            suggested_mode="full",
            computation_time_sec=elapsed,
            notes="ic_only",
        )

    current_mean = sum(data) / len(data)

    should_retrain = False
    reason: Literal["ok", "ic_below_floor", "ic_drop_ratio_exceeded"] = "ok"

    # Priority 1: check ic_below_floor
    if current_mean < ic_floor:
        should_retrain = True
        reason = "ic_below_floor"
    # Priority 2: check ic_drop_ratio (only when reference is meaningful)
    elif reference_ic_mean is not None and reference_ic_mean > 0:
        drop_ratio = (reference_ic_mean - current_mean) / reference_ic_mean
        if drop_ratio > ic_drop_ratio:
            should_retrain = True
            reason = "ic_drop_ratio_exceeded"

    elapsed = time.perf_counter() - t0
    return TriggerDecision(
        should_retrain=should_retrain,
        reason=reason,
        suggested_mode="full",
        computation_time_sec=elapsed,
        notes="ic_only",
    )


# ---------------------------------------------------------------------------
# PerfMonitor class (interfaces.md §3.12)
# ---------------------------------------------------------------------------


class PerfMonitor:
    """IC-based performance monitor wrapping detect_perf_decay.

    Per interfaces.md §3.12.

    Args:
        config: SchedulerConfig with ic_floor, ic_drop_ratio, ic_window.
        ic_history_provider: Callable(window: int) -> list[float] that returns
            recent IC values for the given window size.
    """

    def __init__(
        self,
        config: SchedulerConfig,
        ic_history_provider: Callable[[int], list[float]],
    ) -> None:
        self._config = config
        self._ic_history_provider = ic_history_provider

    def trigger_perf_degradation(self) -> TriggerDecision:
        """Evaluate IC-based performance decay and return a trigger decision.

        Calls ic_history_provider for recent IC data and optionally for
        a reference window to compute the drop ratio.

        Returns:
            TriggerDecision with should_retrain, reason, and notes="ic_only".
        """
        recent_ic = self._ic_history_provider(self._config.ic_window)

        # Reference mean from earlier portion of a longer lookback
        ref_window = self._config.ic_window * 2
        ref_data = self._ic_history_provider(ref_window)
        ref_mean: float | None = None
        if ref_data and len(ref_data) >= self._config.ic_window:
            early_data = ref_data[: self._config.ic_window]
            ref_mean = sum(early_data) / len(early_data)

        return detect_perf_decay(
            recent_ic,
            reference_ic_mean=ref_mean,
            ic_floor=self._config.ic_floor,
            ic_drop_ratio=self._config.ic_drop_ratio,
            window=self._config.ic_window,
        )
