"""Unit tests for FR-1900 performance decay detection (Round-2 IC-only).

Per acceptance.md FR-1900 AC-1~AC-4, interfaces.md §1.7, §3.12.
Round-2 lock: NO Sharpe logic; notes must contain "ic_only".
"""

import time
from unittest.mock import MagicMock

import pytest

from trader_off.scheduler.core import SchedulerConfig
from trader_off.scheduler.perf_monitor import (
    PerfMonitor,
    TriggerDecision,
    detect_perf_decay,
)

# ---------------------------------------------------------------------------
# detect_perf_decay pure-function tests
# ---------------------------------------------------------------------------


class TestDetectPerfDecay:
    """Unit tests for the pure-function detect_perf_decay logic."""

    # -- AC-FR1900-01 -------------------------------------------------------

    def test_ac_fr1900_01_no_trigger_when_above_floor(self):
        """AC-1: IC mean above ic_floor → should_retrain=False, reason="ok".

        Given: recent 20-day IC sequence (mean 0.025, std 0.005),
               ic_floor=0.005, ic_drop_ratio=0.3.
        When: detect_perf_decay(recent_ic, ...).
        Then: should_retrain=False, reason="ok", suggested_mode="full".
        """
        recent_ic = [0.025] * 20  # mean=0.025 > ic_floor=0.005
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3
        )

        assert decision.should_retrain is False
        assert decision.reason == "ok"
        assert decision.suggested_mode == "full"

    # -- AC-FR1900-02 -------------------------------------------------------

    def test_ac_fr1900_02_trigger_below_floor(self):
        """AC-2: IC mean below ic_floor → should_retrain=True, reason="ic_below_floor".

        Given: recent 20-day IC mean drops to -0.01 (below ic_floor=0.005).
        When: detect_perf_decay(recent_ic, ...).
        Then: should_retrain=True, reason="ic_below_floor", suggested_mode="full".
        """
        recent_ic = [-0.01] * 20  # mean=-0.01 < ic_floor=0.005
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3
        )

        assert decision.should_retrain is True
        assert decision.reason == "ic_below_floor"
        assert decision.suggested_mode == "full"

    # -- AC-FR1900-03 -------------------------------------------------------

    def test_ac_fr1900_03_trigger_drop_ratio(self):
        """AC-3: IC drop ≥30% → should_retrain=True, reason="ic_drop_ratio_exceeded".

        Given: current 20-day IC mean 0.025, 30-day-ago mean 0.05,
               ic_drop_ratio=0.3 (drop 50% > 30% threshold).
        When: detect_perf_decay(recent_ic, reference_ic_mean=0.05, ...).
        Then: should_retrain=True, reason="ic_drop_ratio_exceeded".
        """
        recent_ic = [0.025] * 20  # current mean = 0.025
        # reference mean = 0.05, drop = (0.05-0.025)/0.05 = 0.5 > 0.3
        decision = detect_perf_decay(
            recent_ic,
            reference_ic_mean=0.05,
            ic_floor=0.005,
            ic_drop_ratio=0.3,
        )

        assert decision.should_retrain is True
        assert decision.reason == "ic_drop_ratio_exceeded"

    # -- AC-FR1900-04 (Round-2 lock) ----------------------------------------

    def test_ac_fr1900_04_round2_lock_no_sharpe_ic_only_fast(self):
        """AC-4: Round-2 lock — no sharpe field, notes contain 'ic_only', <1s.

        Given: user confirmed FR-1900 IC-only (no Sharpe).
        When: detect_perf_decay() called.
        Then: decision has no sharpe attribute, notes contain "ic_only",
              computation_time_sec < 1.0.
        """
        recent_ic = [0.03] * 20

        t0 = time.perf_counter()
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3
        )
        elapsed = time.perf_counter() - t0

        # Round-2 lock: absolutely no sharpe field
        assert not hasattr(decision, "sharpe")
        # Round-2 lock: notes must contain "ic_only"
        assert "ic_only" in decision.notes
        # Computation must be fast (no sub-backtest overhead)
        assert decision.computation_time_sec < 1.0
        assert elapsed < 1.0

    # -- Edge cases ---------------------------------------------------------

    def test_no_trigger_when_reference_not_provided(self):
        """When reference_ic_mean is None and IC above floor, no trigger."""
        recent_ic = [0.03] * 20
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3
        )

        assert decision.should_retrain is False
        assert decision.reason == "ok"

    def test_drop_ratio_not_exceeded(self):
        """When drop ratio is below threshold, no ic_drop_ratio trigger."""
        recent_ic = [0.045] * 20  # current mean = 0.045
        # reference mean = 0.05, drop = 10% < 30% threshold
        decision = detect_perf_decay(
            recent_ic,
            reference_ic_mean=0.05,
            ic_floor=0.005,
            ic_drop_ratio=0.3,
        )

        assert decision.should_retrain is False
        assert decision.reason == "ok"

    def test_rolling_mean_with_fewer_than_window(self):
        """Rolling mean uses only available data when fewer than window."""
        recent_ic = [0.03] * 5  # only 5 values, mean = 0.03 > 0.005
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3, window=20
        )

        assert decision.should_retrain is False

    def test_rolling_mean_uses_last_window(self):
        """Only the last `window` values contribute to the rolling mean."""
        # 30 values: first 10 are low, last 20 are high
        recent_ic = [0.0] * 10 + [0.03] * 20
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3, window=20
        )

        assert decision.should_retrain is False  # mean of last 20 = 0.03 > 0.005

    def test_empty_ic_list_returns_ok(self):
        """Empty IC list should return ok (no data → no trigger)."""
        decision = detect_perf_decay(
            [], ic_floor=0.005, ic_drop_ratio=0.3
        )

        assert decision.should_retrain is False
        assert decision.reason == "ok"

    def test_ic_floor_exactly_equal_not_triggered(self):
        """When IC mean exactly equals ic_floor, should NOT trigger."""
        recent_ic = [0.005] * 20
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3
        )

        assert decision.should_retrain is False

    def test_ic_just_below_floor_triggered(self):
        """When IC mean is slightly below floor, should trigger."""
        recent_ic = [0.004] * 20
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3
        )

        assert decision.should_retrain is True
        assert decision.reason == "ic_below_floor"

    def test_ic_below_floor_takes_priority_over_drop(self):
        """When both conditions hold, ic_below_floor takes priority."""
        recent_ic = [-0.01] * 20  # below ic_floor=0.005
        decision = detect_perf_decay(
            recent_ic,
            reference_ic_mean=0.05,
            ic_floor=0.005,
            ic_drop_ratio=0.3,
        )

        assert decision.should_retrain is True
        assert decision.reason == "ic_below_floor"

    def test_notes_always_contains_ic_only(self):
        """Every TriggerDecision must have 'ic_only' in notes."""
        recent_ic = [0.03] * 20
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3
        )

        assert "ic_only" in decision.notes

    def test_triggered_decision_has_ic_only(self):
        """Triggered decisions also contain 'ic_only'."""
        recent_ic = [-0.01] * 20
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3
        )

        assert decision.should_retrain is True
        assert "ic_only" in decision.notes

    def test_reference_zero_mean_no_drop_error(self):
        """When reference_ic_mean is 0, drop ratio calculation is skipped."""
        recent_ic = [0.025] * 20
        decision = detect_perf_decay(
            recent_ic,
            reference_ic_mean=0.0,
            ic_floor=0.005,
            ic_drop_ratio=0.3,
        )

        assert decision.should_retrain is False
        assert decision.reason == "ok"

    def test_reference_negative_mean_skips_drop(self):
        """When reference_ic_mean is negative, drop ratio is skipped."""
        recent_ic = [-0.01] * 20
        decision = detect_perf_decay(
            recent_ic,
            reference_ic_mean=-0.02,
            ic_floor=-0.05,  # lowered floor so only drop could trigger
            ic_drop_ratio=0.3,
        )

        # recent mean=-0.01 > ic_floor=-0.05, and reference negative → no drop check
        assert decision.reason == "ok"

    def test_computation_time_sec_is_set(self):
        """computation_time_sec field is populated with a non-negative float."""
        recent_ic = [0.025] * 20
        decision = detect_perf_decay(
            recent_ic, ic_floor=0.005, ic_drop_ratio=0.3
        )

        assert decision.computation_time_sec >= 0.0
        assert isinstance(decision.computation_time_sec, float)

    def test_trigger_decision_dataclass_is_frozen(self):
        """TriggerDecision must be frozen (immutable) per interfaces.md §1.7."""
        decision = TriggerDecision(
            should_retrain=False,
            reason="ok",
            suggested_mode="full",
            computation_time_sec=0.001,
            notes="ic_only",
        )

        with pytest.raises(Exception):
            decision.should_retrain = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PerfMonitor class tests
# ---------------------------------------------------------------------------


class TestPerfMonitor:
    """Tests for the PerfMonitor class that wraps detect_perf_decay."""

    def test_trigger_delegates_to_detect_perf_decay(self):
        """PerfMonitor.trigger_perf_degradation calls provider and returns TriggerDecision."""
        config = SchedulerConfig(
            ic_floor=0.005, ic_drop_ratio=0.3, ic_window=20
        )
        mock_provider = MagicMock(return_value=[0.025] * 20)

        monitor = PerfMonitor(config, mock_provider)
        decision = monitor.trigger_perf_degradation()

        mock_provider.assert_called()
        assert isinstance(decision, TriggerDecision)
        assert decision.should_retrain is False
        assert decision.reason == "ok"
        assert "ic_only" in decision.notes
        assert not hasattr(decision, "sharpe")

    def test_trigger_with_provider_returning_below_floor(self):
        """Provider returns below-floor IC → should trigger."""
        config = SchedulerConfig(
            ic_floor=0.005, ic_drop_ratio=0.3, ic_window=20
        )
        mock_provider = MagicMock(return_value=[-0.01] * 20)

        monitor = PerfMonitor(config, mock_provider)
        decision = monitor.trigger_perf_degradation()

        assert decision.should_retrain is True
        assert decision.reason == "ic_below_floor"

    def test_trigger_with_drop_detection(self):
        """PerfMonitor detects drop when reference and current IC differ."""
        config = SchedulerConfig(
            ic_floor=0.005, ic_drop_ratio=0.3, ic_window=20,
        )
        # First call (window=20) → recent IC; second call (window=40) → reference
        call_count = 0

        def mock_provider(n: int) -> list[float]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [0.025] * 20  # recent
            else:
                return [0.05] * 40  # reference

        monitor = PerfMonitor(config, mock_provider)
        decision = monitor.trigger_perf_degradation()

        assert decision.should_retrain is True
        assert decision.reason == "ic_drop_ratio_exceeded"

    def test_init_stores_config_and_provider(self):
        """Constructor stores config and ic_history_provider."""
        config = SchedulerConfig()
        provider = MagicMock()

        monitor = PerfMonitor(config, provider)

        assert monitor._config is config
        assert monitor._ic_history_provider is provider
